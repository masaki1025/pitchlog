"""TSK-550のS0〜S3順序を隔離DBだけで実行する候補入口。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, LiteralString, cast

import psycopg
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from pitchlog.authz.product_provisioning import (
    apply_product_authz_before_rule_placement,
)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PLACEMENT = Path(__file__).with_name("tsk550_stage_a_rule_defaults.py")
_AUTHZ = Path(__file__).with_name("tsk550_authz")
_S0_REVISION = "0032_rg1_restore_gate"
_FUNCTION_ID = "FUNCTION:public:resolve_stage_a_rule(uuid, text, text, boolean)"
_ASSET_SET_SHA256 = "3715c946ad00f165044db9c6e9e3bb4825ad2c1ab159a17a7a3209886b7f48a6"
_PLACEMENT_SHA256 = "631e253ebaa69fb93449780e0d43ab14e069b4dffa2f02881919af08ff7f8974"


class StageAStartupCandidateError(RuntimeError):
    """段階起動候補が前提を満たさないときの停止。"""


@dataclass(frozen=True, slots=True)
class CandidateStageAResult:
    """S3までの隔離候補結果。S4公開可を表現しない。"""

    completed_stage: str = "S3"
    publishable: bool = False


@dataclass(frozen=True, slots=True)
class _CandidateAssets:
    """適用前に照合した候補内容を再読込せず保持する。"""

    placement: bytes
    authz: tuple[bytes, ...]


def _require_candidate_assets() -> _CandidateAssets:
    """候補の固定配置と17資産の完全な集合・内容を照合する。"""
    placement = _PLACEMENT.read_bytes()
    if sha256(placement).hexdigest() != _PLACEMENT_SHA256:
        raise StageAStartupCandidateError("S2配置候補のSHAが不一致です")
    assets = sorted(_AUTHZ.rglob("*.sql"))
    if len(assets) != 17:
        raise StageAStartupCandidateError("S3候補資産は17件が必要です")
    digest = sha256()
    contents = {asset: asset.read_bytes() for asset in assets}
    for asset in assets:
        digest.update(str(asset.relative_to(_AUTHZ)).encode())
        digest.update(b"\0")
        digest.update(contents[asset])
        digest.update(b"\0")
    if digest.hexdigest() != _ASSET_SET_SHA256:
        raise StageAStartupCandidateError("S3候補資産の集合または内容が不一致です")
    ordered = (
        _AUTHZ / "roles/pitchlog_rule_resolution_fn_owner.sql",
        *sorted((_AUTHZ / "column_acl_expectations").glob("*.sql")),
        _AUTHZ / "functions" / f"{_FUNCTION_ID}.sql",
    )
    if set(ordered) != set(assets):
        raise StageAStartupCandidateError("S3候補資産の適用順が不一致です")
    return _CandidateAssets(placement, tuple(contents[asset] for asset in ordered))


def _require_same_database(owner_dsn: str, applicator_dsn: str) -> None:
    """ownerと認可適用主体が同じTCP上のDB実体を指すか照合する。"""
    owner_parts = conninfo_to_dict(owner_dsn)
    applicator_parts = conninfo_to_dict(applicator_dsn)
    coordinates = ("host", "port", "dbname")
    if any(
        not owner_parts.get(key) or owner_parts.get(key) != applicator_parts.get(key)
        for key in coordinates
    ):
        raise StageAStartupCandidateError("S0/S1の接続先が一致しません")
    identity_sql = (
        "SELECT inet_server_addr()::text, inet_server_port(), "
        "current_database(), d.oid, pg_postmaster_start_time() "
        "FROM pg_catalog.pg_database d WHERE d.datname = current_database()"
    )
    with (
        psycopg.connect(owner_dsn) as owner,
        psycopg.connect(applicator_dsn) as applicator,
    ):
        with owner.cursor() as cursor:
            cursor.execute(identity_sql)
            owner_identity = cursor.fetchone()
        with applicator.cursor() as cursor:
            cursor.execute(identity_sql)
            applicator_identity = cursor.fetchone()
    if (
        owner_identity is None
        or owner_identity[0] is None
        or owner_identity[1] is None
        or owner_identity != applicator_identity
    ):
        raise StageAStartupCandidateError("S0/S1のDB実体が一致しません")


def _owner_url(owner_dsn: str) -> URL:
    """既存のowner接続をAlembic候補へ渡す。"""
    parts = conninfo_to_dict(owner_dsn)
    if any(parts.get(key) is None for key in ("user", "host", "port", "dbname")):
        raise StageAStartupCandidateError("owner DSNの接続先が不足しています")
    if parts["user"] != "pitchlog_owner":
        raise StageAStartupCandidateError("S2はpitchlog_owner接続だけで実行します")
    return URL.create(
        "postgresql+psycopg",
        username=str(parts["user"]),
        password=None if parts.get("password") is None else str(parts["password"]),
        host=str(parts["host"]),
        port=int(str(parts["port"])),
        database=str(parts["dbname"]),
    )


def _require_s0(owner_dsn: str) -> None:
    """S0の正確なrevisionと認可適用前の状態を確かめる。"""
    with psycopg.connect(owner_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user, session_user")
            if cursor.fetchone() != ("pitchlog_owner", "pitchlog_owner"):
                raise StageAStartupCandidateError("S0のowner認証主体が不一致です")
            cursor.execute("SELECT version_num FROM public.alembic_version")
            if cursor.fetchall() != [(_S0_REVISION,)]:
                raise StageAStartupCandidateError("S0のschema revisionが不一致です")
            cursor.execute(
                "SELECT relforcerowsecurity FROM pg_catalog.pg_class "
                "WHERE oid IN ('public.rule_sets'::regclass, "
                "'public.game_type_rule_defaults'::regclass)"
            )
            if cursor.fetchall() != [(False,), (False,)]:
                raise StageAStartupCandidateError("S0は認可適用前の2表が必要です")


def _require_s1(applicator: psycopg.Connection[Any]) -> None:
    """製品認可のcommit後に配置対象のFORCE RLSを照合する。"""
    with applicator.cursor() as cursor:
        cursor.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity "
            "FROM pg_catalog.pg_class "
            "WHERE oid IN ('public.rule_sets'::regclass, "
            "'public.game_type_rule_defaults'::regclass) ORDER BY relname"
        )
        if cursor.fetchall() != [
            ("game_type_rule_defaults", True, True),
            ("rule_sets", True, True),
        ]:
            raise StageAStartupCandidateError("S1のFORCE RLSが不一致です")
    applicator.rollback()


def _require_s3(applicator: psycopg.Connection[Any]) -> None:
    """候補関数のownerと公開EXECUTEを照合し、候補公開は許さない。"""
    with applicator.cursor() as cursor:
        cursor.execute(
            "SELECT pg_catalog.pg_get_userbyid(p.proowner), p.prosecdef, "
            "pg_catalog.has_function_privilege('pitchlog_app', p.oid, 'EXECUTE'), "
            "pg_catalog.has_function_privilege('pitchlog_owner', p.oid, 'EXECUTE') "
            "FROM pg_catalog.pg_proc p WHERE p.oid = "
            "'public.resolve_stage_a_rule(uuid,text,text,boolean)'::regprocedure"
        )
        if cursor.fetchone() != (
            "pitchlog_rule_resolution_fn_owner",
            True,
            True,
            False,
        ):
            raise StageAStartupCandidateError("S3候補関数の権限が不一致です")
    applicator.rollback()


def _apply_placement(owner_dsn: str, source: bytes) -> None:
    """候補Aだけをowner transactionで適用する。"""
    namespace: dict[str, Any] = {
        "__file__": str(_PLACEMENT),
        "__name__": "tsk550_stage_a_rule_defaults_candidate",
    }
    exec(compile(source, str(_PLACEMENT), "exec"), namespace)
    upgrade = namespace["upgrade"]
    engine = create_engine(_owner_url(owner_dsn))
    try:
        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                upgrade()
    finally:
        engine.dispose()


def _apply_candidate_authz(
    applicator: psycopg.Connection[Any], assets: tuple[bytes, ...]
) -> None:
    """17候補資産をS2とは別transactionで適用する。"""
    if len(assets) != 17:
        raise StageAStartupCandidateError("S3候補資産は17件が必要です")
    try:
        with applicator.cursor() as cursor:
            cursor.execute(sql.SQL(cast(LiteralString, assets[0].decode())))
            # 正式schema資産はU-R1所有解除後に追加する。
            cursor.execute(
                "GRANT USAGE ON SCHEMA public TO pitchlog_rule_resolution_fn_owner"
            )
            for asset in assets[1:]:
                cursor.execute(sql.SQL(cast(LiteralString, asset.decode())))
        applicator.commit()
    except Exception:
        applicator.rollback()
        raise


def advance_stage_a_candidate_from_s0(
    *, owner_dsn: str, applicator_dsn: str
) -> CandidateStageAResult:
    """S0済み隔離DBでS1→S2→S3を実行し、S4公開を拒否したまま返す。

    Args:
        owner_dsn: 既存schemaのowner認証接続。
        applicator_dsn: 製品認可を適用できる管理接続。

    Returns:
        S3までの候補結果。製品の公開許可ではない。

    Raises:
        StageAStartupCandidateError: revision・認可前提が不一致のとき。
    """
    assets = _require_candidate_assets()
    _require_same_database(owner_dsn, applicator_dsn)
    _require_s0(owner_dsn)
    with psycopg.connect(applicator_dsn) as applicator:
        apply_product_authz_before_rule_placement(applicator)
        _require_s1(applicator)
        _apply_placement(owner_dsn, assets.placement)
        _apply_candidate_authz(applicator, assets.authz)
        _require_s3(applicator)
    return CandidateStageAResult()
