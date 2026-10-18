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
_PRE_PLACEMENT_REVISION = "0032_rg1_restore_gate"
_PLACEMENT_REVISION = "0033_stage_a_rule_defaults"
_PLACEMENT_SOURCE = _BACKEND_ROOT / "migrations/versions/0033_stage_a_rule_defaults.py"


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


def _require_s3(applicator_dsn: str) -> None:
    """適用後も公開せずrevisionと認可カタログの全期待値を照合する。"""
    with psycopg.connect(applicator_dsn) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version_num FROM public.alembic_version")
        if cursor.fetchall() != [(_PLACEMENT_REVISION,)]:
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


def _require_placed_state(applicator_dsn: str) -> None:
    """S2後の再開前に配置と一時権限の完全一致を確認する。"""
    rules = run_path(str(_PLACEMENT_SOURCE))["_RULES"]
    if not isinstance(rules, tuple) or len(rules) != 5:
        raise StageAStartupError("配置契約の固定5組を取得できません")
    keys = [row[0] for row in rules]
    ids = [row[1] for row in rules]
    with psycopg.connect(applicator_dsn) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version_num FROM public.alembic_version")
        if cursor.fetchall() != [(_PLACEMENT_REVISION,)]:
            raise StageAStartupError("S2確定後のschema revisionが不一致です")
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


def resume_stage_a_after_placement(
    *, owner_dsn: str, applicator_dsn: str
) -> StageAStartupResult:
    """S2確定後の状態を照合し、S3だけを再適用して非公開で戻る。"""
    _require_same_database(owner_dsn, applicator_dsn)
    with psycopg.connect(owner_dsn) as owner, owner.cursor() as cursor:
        cursor.execute("SELECT current_user, session_user")
        if cursor.fetchone() != ("pitchlog_owner", "pitchlog_owner"):
            raise StageAStartupError("S3再開にはpitchlog_owner接続が必要です")
    _require_placed_state(applicator_dsn)
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
    with psycopg.connect(applicator_dsn) as applicator:
        apply_product_authz_ddl(applicator)
    _require_s3(applicator_dsn)
    return StageAStartupResult()
