"""規則配置を認可適用より先に確定する段階起動入口。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from runpy import run_path
from typing import Any

import psycopg
from alembic import command
from alembic.config import Config
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from pitchlog.authz.product_catalog import inspect_product_authz_catalog
from pitchlog.authz.product_provisioning import (
    apply_product_authz_before_rule_placement,
    apply_product_authz_ddl,
)

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_PRE_PLACEMENT_REVISION = "0033_game_rules_immutable"
_PLACEMENT_REVISION = "0034_stage_a_rule_defaults"
_EPOCH_REVISION = "0035_rg1_initial_fresh_epoch"
_INITIAL_REVISION = "0036_initial_right_storage"
_PLACEMENT_SOURCE = _BACKEND_ROOT / "migrations/versions/0034_stage_a_rule_defaults.py"


class StageAStartupError(RuntimeError):
    """段階起動の前提不一致または未確認状態を表す。"""


@dataclass(frozen=True, slots=True)
class StageAStartupResult:
    """S3までの結果。公開許可は別のS4照合で決める。"""

    completed_stage: str = "S3"
    publishable: bool = False


def _require_same_database(owner_dsn: str, applicator_dsn: str) -> None:
    """異なるDBにS1とS2を分割適用しない。"""
    owner_parts = conninfo_to_dict(owner_dsn)
    applicator_parts = conninfo_to_dict(applicator_dsn)
    if any(
        not owner_parts.get(key) or owner_parts.get(key) != applicator_parts.get(key)
        for key in ("host", "port", "dbname")
    ):
        raise StageAStartupError("S1とS2の接続先が一致しません")
    identity_sql = (
        "SELECT inet_server_addr()::text, inet_server_port(), "
        "current_database(), d.oid, pg_postmaster_start_time() "
        "FROM pg_catalog.pg_database d WHERE d.datname = current_database()"
    )
    identities: list[tuple[Any, ...] | None] = []
    for dsn in (owner_dsn, applicator_dsn):
        with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
            cursor.execute(identity_sql)
            identities.append(cursor.fetchone())
    if (
        identities[0] is None
        or identities[0][0] is None
        or identities[0] != identities[1]
    ):
        raise StageAStartupError("S1とS2のDB実体が一致しません")


def _require_s0(owner_dsn: str) -> None:
    """owner主体と配置前revisionを厳密に確認する。"""
    with psycopg.connect(owner_dsn) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT current_user, session_user")
        if cursor.fetchone() != ("pitchlog_owner", "pitchlog_owner"):
            raise StageAStartupError("S2にはpitchlog_owner接続が必要です")
        cursor.execute("SELECT version_num FROM public.alembic_version")
        if cursor.fetchall() != [(_PRE_PLACEMENT_REVISION,)]:
            raise StageAStartupError("S0のschema revisionが不一致です")


def _owner_url(owner_dsn: str) -> URL:
    """Alembicへ検証済みowner接続を渡す。"""
    parts = conninfo_to_dict(owner_dsn)
    if any(parts.get(key) is None for key in ("user", "host", "port", "dbname")):
        raise StageAStartupError("owner接続の識別子が不足しています")
    if parts["user"] != "pitchlog_owner":
        raise StageAStartupError("S2の接続主体が不正です")
    return URL.create(
        "postgresql+psycopg",
        username=str(parts["user"]),
        password=None if parts.get("password") is None else str(parts["password"]),
        host=str(parts["host"]),
        port=int(str(parts["port"])),
        database=str(parts["dbname"]),
    )


def _apply_placement(owner_dsn: str) -> None:
    """配置migrationとrevisionを同一transactionで確定する。"""
    engine = create_engine(_owner_url(owner_dsn))
    try:
        with engine.begin() as connection:
            config = Config(str(_BACKEND_ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, _PLACEMENT_REVISION)
    finally:
        engine.dispose()


def _apply_epoch(owner_dsn: str) -> None:
    """0034の確定後にownerで0035だけをtransaction内適用する。"""
    engine = create_engine(_owner_url(owner_dsn))
    try:
        with engine.begin() as connection:
            config = Config(str(_BACKEND_ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, _EPOCH_REVISION)
    finally:
        engine.dispose()


def _require_epoch_state(applicator_dsn: str) -> None:
    """改訂markerだけでなく0035の実列と制約を閉集合で照合する。"""
    with psycopg.connect(applicator_dsn) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version_num FROM public.alembic_version")
        if cursor.fetchall() not in ([(_EPOCH_REVISION,)], [(_INITIAL_REVISION,)]):
            raise StageAStartupError("epoch適用後のschema revisionが不一致です")
        cursor.execute(
            "SELECT a.atttypid::regtype::text, a.attnotnull, a.attidentity, "
            "a.attgenerated, pg_get_expr(d.adbin, d.adrelid) "
            "FROM pg_catalog.pg_attribute a "
            "LEFT JOIN pg_catalog.pg_attrdef d "
            "ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
            "WHERE a.attrelid = 'public.rg1_restore_gate'::regclass "
            "AND a.attname = 'recovery_generation' AND NOT a.attisdropped"
        )
        if cursor.fetchall() != [("bigint", False, "", "", None)]:
            raise StageAStartupError("0035のepoch実列定義が不一致です")
        cursor.execute(
            "SELECT pg_get_constraintdef(oid), convalidated, connoinherit "
            "FROM pg_catalog.pg_constraint "
            "WHERE conrelid = 'public.rg1_restore_gate'::regclass "
            "AND conname = 'ck_rg1_restore_gate_recovery_generation' "
            "AND contype = 'c'"
        )
        if cursor.fetchall() != [
            (
                "CHECK (((recovery_generation IS NULL) OR (recovery_generation > 0)))",
                True,
                False,
            )
        ]:
            raise StageAStartupError("0035のepoch実制約が不一致です")


def _require_s3(applicator_dsn: str) -> None:
    """適用後も公開せずrevisionと認可カタログの全期待値を照合する。"""
    with psycopg.connect(applicator_dsn) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version_num FROM public.alembic_version")
        if cursor.fetchall() != [(_INITIAL_REVISION,)]:
            raise StageAStartupError("S3のschema revisionが不一致です")
        cursor.execute(
            "SELECT p.proowner::regrole::text, p.prosecdef "
            "FROM pg_catalog.pg_proc p "
            "WHERE p.oid = pg_catalog.to_regprocedure("
            "'public.resolve_stage_a_rule(uuid,text,text,boolean)')"
        )
        if cursor.fetchone() != ("pitchlog_rule_resolution_fn_owner", True):
            raise StageAStartupError("S3の関数所有者またはSECURITY DEFINERが不一致です")
        cursor.execute(
            "SELECT oid FROM pg_catalog.pg_roles WHERE rolname = current_user"
        )
        row = cursor.fetchone()
        if row is None or type(row[0]) is not int:
            raise StageAStartupError("S3の認可検査主体を確認できません")
        report = inspect_product_authz_catalog(
            connection, privileged_role_oids=frozenset({row[0]})
        )
        if not report.ok:
            raise StageAStartupError("S3の製品認可カタログが不一致です")


def _require_placed_state(applicator_dsn: str) -> str:
    """S2後の再開前に配置と一時権限の完全一致を確認する。"""
    rules = run_path(str(_PLACEMENT_SOURCE))["_RULES"]
    if not isinstance(rules, tuple) or len(rules) != 5:
        raise StageAStartupError("配置契約の固定5組を取得できません")
    keys = [row[0] for row in rules]
    ids = [row[1] for row in rules]
    with psycopg.connect(applicator_dsn) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version_num FROM public.alembic_version")
        revisions = cursor.fetchall()
        if revisions not in (
            [(_PLACEMENT_REVISION,)],
            [(_EPOCH_REVISION,)],
            [(_INITIAL_REVISION,)],
        ):
            raise StageAStartupError("S2確定後のschema revisionが不一致です")
        revision = str(revisions[0][0])
        cursor.execute(
            "SELECT id::text, regulation_innings, called_game_conditions, "
            "extra_innings_limit, tiebreak_rule, uses_dh "
            "FROM public.rule_sets WHERE id = ANY(%s::uuid[]) ORDER BY id::text",
            (ids,),
        )
        expected_rules = sorted(
            (rule_id, 9, cold, limit, tiebreak, True)
            for _, rule_id, cold, limit, tiebreak in rules
        )
        if cursor.fetchall() != expected_rules:
            raise StageAStartupError("S2の固定規則5行が不一致です")
        cursor.execute(
            "SELECT game_type_key, game_type_category, rule_set_id::text "
            "FROM public.game_type_rule_defaults "
            "WHERE game_type_key = ANY(%s) ORDER BY game_type_key",
            (keys,),
        )
        expected_defaults = sorted(
            (key, "game_type", rule_id) for key, rule_id, *_ in rules
        )
        if cursor.fetchall() != expected_defaults:
            raise StageAStartupError("S2の固定既定5行が不一致です")
        cursor.execute(
            "SELECT relname, pg_get_userbyid(relowner), relrowsecurity, "
            "relforcerowsecurity FROM pg_catalog.pg_class "
            "WHERE oid IN ('public.rule_sets'::regclass, "
            "'public.game_type_rule_defaults'::regclass) ORDER BY relname"
        )
        if cursor.fetchall() != [
            ("game_type_rule_defaults", "pitchlog_owner", True, True),
            ("rule_sets", "pitchlog_owner", True, True),
        ]:
            raise StageAStartupError("S2の表ownerまたはRLSが不一致です")
        cursor.execute(
            "SELECT policyname FROM pg_catalog.pg_policies "
            "WHERE schemaname = 'public' AND policyname LIKE 'tsk550_seed_%'"
        )
        if cursor.fetchone() is not None:
            raise StageAStartupError("S2の一時policyが残っています")
    return revision


def resume_stage_a_after_placement(
    *, owner_dsn: str, applicator_dsn: str
) -> StageAStartupResult:
    """既配置を検査し、必要な0035/0036とS3だけを適用して非公開で戻る。"""
    _require_same_database(owner_dsn, applicator_dsn)
    with psycopg.connect(owner_dsn) as owner, owner.cursor() as cursor:
        cursor.execute("SELECT current_user, session_user")
        if cursor.fetchone() != ("pitchlog_owner", "pitchlog_owner"):
            raise StageAStartupError("S3再開にはpitchlog_owner接続が必要です")
    revision = _require_placed_state(applicator_dsn)
    if revision == _PLACEMENT_REVISION:
        _apply_epoch(owner_dsn)
    _require_epoch_state(applicator_dsn)
    if revision != _INITIAL_REVISION:
        _apply_initial_storage(owner_dsn)
    _require_initial_state(applicator_dsn)
    with psycopg.connect(applicator_dsn) as applicator:
        apply_product_authz_ddl(applicator)
    _require_placed_state(applicator_dsn)
    _require_s3(applicator_dsn)
    return StageAStartupResult()


def advance_stage_a_from_s0(
    *, owner_dsn: str, applicator_dsn: str
) -> StageAStartupResult:
    """S0からS1認可、S2配置、S3全認可を別transactionで実行する。

    Args:
        owner_dsn: `pitchlog_owner`の配置用接続。
        applicator_dsn: 既存認可適用器のsuperuser接続。

    Returns:
        S3到達を表す非公開結果。

    Raises:
        StageAStartupError: 接続先、主体、revision、関数の不一致。
    """
    _require_same_database(owner_dsn, applicator_dsn)
    _require_s0(owner_dsn)
    with psycopg.connect(applicator_dsn) as applicator:
        apply_product_authz_before_rule_placement(applicator)
    _apply_placement(owner_dsn)
    _require_placed_state(applicator_dsn)
    _apply_epoch(owner_dsn)
    _require_epoch_state(applicator_dsn)
    _apply_initial_storage(owner_dsn)
    _require_initial_state(applicator_dsn)
    with psycopg.connect(applicator_dsn) as applicator:
        apply_product_authz_ddl(applicator)
    _require_s3(applicator_dsn)
    return StageAStartupResult()


def _apply_initial_storage(owner_dsn: str) -> None:
    """0035確認後にownerで0036だけをtransaction内適用する。"""
    engine = create_engine(_owner_url(owner_dsn))
    try:
        with engine.begin() as connection:
            config = Config(str(_BACKEND_ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, _INITIAL_REVISION)
    finally:
        engine.dispose()


def _require_initial_state(applicator_dsn: str) -> None:
    """36markerだけの偽装を拒否し、新2列/制約/4表/triggerを実照合する。"""
    with psycopg.connect(applicator_dsn) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version_num FROM public.alembic_version")
        if cursor.fetchall() != [(_INITIAL_REVISION,)]:
            raise StageAStartupError("0036のschema revisionが不一致です")
        cursor.execute(
            "SELECT a.attname, a.atttypid::regtype::text, a.attnotnull, "
            "a.attidentity, a.attgenerated, pg_get_expr(d.adbin, d.adrelid) "
            "FROM pg_catalog.pg_attribute a LEFT JOIN pg_catalog.pg_attrdef d "
            "ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
            "WHERE a.attrelid='public.recording_generations'::regclass "
            "AND a.attname IN ('proof_digest','recovery_generation') "
            "AND NOT a.attisdropped ORDER BY a.attname"
        )
        if cursor.fetchall() != [
            ("proof_digest", "bytea", False, "", "", None),
            ("recovery_generation", "bigint", False, "", "", None),
        ]:
            raise StageAStartupError("0036の世代証拠実列が不一致です")
        cursor.execute(
            "SELECT conname, pg_get_constraintdef(oid), convalidated, connoinherit "
            "FROM pg_catalog.pg_constraint "
            "WHERE conrelid='public.recording_generations'::regclass "
            "AND conname IN ('ck_recording_generations_proof_digest', "
            "'ck_recording_generations_recovery_generation') AND contype='c' "
            "ORDER BY conname"
        )
        if cursor.fetchall() != [
            (
                "ck_recording_generations_proof_digest",
                "CHECK (((proof_digest IS NULL) OR (octet_length(proof_digest) = 32)))",
                True,
                False,
            ),
            (
                "ck_recording_generations_recovery_generation",
                "CHECK (((recovery_generation IS NULL) OR (recovery_generation > 0)))",
                True,
                False,
            ),
        ]:
            raise StageAStartupError("0036の世代証拠実制約が不一致です")
        tables = (
            "game_start_attempts",
            "game_start_requests",
            "recording_right_deliveries",
            "trusted_devices",
        )
        cursor.execute(
            "SELECT c.relname, r.rolname, c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace"
            " n ON n.oid=c.relnamespace "
            "JOIN pg_catalog.pg_roles r ON r.oid=c.relowner "
            "WHERE n.nspname='public' AND c.relkind='r' AND c.relnam"
            "e=ANY(%s) ORDER BY c.relname",
            (list(tables),),
        )
        if cursor.fetchall() != [
            (table, "pitchlog_owner", True, True) for table in tables
        ]:
            raise StageAStartupError("0036の4表owner/RLSが不一致です")
        cursor.execute(
            "SELECT c.relname, t.tgname, t.tgenabled, t.tgtype, p.proname, "
            "r.rolname, p.prosecdef, p.proconfig "
            "FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c"
            " ON c.oid=t.tgrelid "
            "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid "
            "JOIN pg_catalog.pg_roles r ON r.oid=p.proowner "
            "WHERE n.nspname='public' AND c.relname=ANY(%s) AND NOT "
            "t.tgisinternal ORDER BY c.relname,t.tgname",
            (list(tables),),
        )
        if cursor.fetchall() != [
            (
                table,
                f"trg_{table}_initial_right_guard",
                "O",
                27,
                "protect_initial_right_storage",
                "pitchlog_owner",
                False,
                ["search_path=pg_catalog, pg_temp"],
            )
            for table in tables
        ]:
            raise StageAStartupError("0036の内部保護triggerが不一致です")

        cursor.execute(
            "SELECT t.tgname, t.tgenabled, t.tgtype, n.nspname, p.proname, "
            "ARRAY(SELECT a.attname FROM unnest(t.tgattr::smallint[]) "
            "WITH ORDINALITY AS member(attnum, ordinal_position) "
            "JOIN pg_catalog.pg_attribute a ON a.attrelid=t.tgrelid "
            "AND a.attnum=member.attnum ORDER BY member.ordinal_position) "
            "FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid "
            "JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace "
            "WHERE t.tgrelid='public.recording_generations'::regclass "
            "AND t.tgname='trg_recording_generations_update_guard' "
            "AND NOT t.tgisinternal"
        )
        if cursor.fetchall() != [
            (
                "trg_recording_generations_update_guard",
                "O",
                19,
                "public",
                "protect_recording_generations_updates",
                [
                    "generation",
                    "kind",
                    "issuance_order",
                    "holder_device",
                    "granted_at",
                    "confirmed_watermark",
                    "proof_digest",
                    "recovery_generation",
                ],
            )
        ]:
            raise StageAStartupError("0036の世代guard発火列が不一致です")
