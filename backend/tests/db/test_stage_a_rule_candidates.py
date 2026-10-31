"""TSK-550段階Aの未登録候補を隔離DBで検証する。"""

from __future__ import annotations

import runpy
import secrets
import shutil
import traceback
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, LiteralString, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from db_fixtures import _require_historical_cluster
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import URL
from test_authz_tenant_context import make_tenant_context

from pitchlog.authz.product_provisioning import (
    apply_product_authz_before_rule_placement,
)
from pitchlog.db.engine import create_database_engine
from pitchlog.db.game_state.rule_snapshot import (
    decode_structure,
    encode_applied_rules,
    validate_correlations,
)
from pitchlog.db.stage_a_startup import (
    StageAStartupError,
    advance_stage_a_from_s0,
    resume_stage_a_after_placement,
)
from pitchlog.repositories import transaction
from pitchlog.repositories.rule_resolution import (
    RuleResolutionError,
    StageARuleRequest,
    resolve_stage_a_rule,
)

from .conftest import DisposablePostgres

pytestmark = pytest.mark.requires_db

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_CANDIDATE = _BACKEND_ROOT / "migrations/candidates/tsk550_stage_a_rule_defaults.py"
_FUNCTION = _BACKEND_ROOT / "migrations/candidates/tsk550_resolve_stage_a_rule.sql"
_FUNCTION_ASSETS = _BACKEND_ROOT / "migrations/candidates/tsk550_authz"
_STARTUP = _BACKEND_ROOT / "migrations/candidates/tsk550_stage_a_startup.py"
_OFFICIAL_ID = UUID("ca626b2e-8751-530e-a431-9ef5c00f7d95")


@dataclass(frozen=True)
class _CandidateCatalog:
    """候補試験が使うS1時点の隔離接続。"""

    owner_dsn: str
    applicator: psycopg.Connection[Any]
    observer: psycopg.Connection[Any]


@pytest.fixture
def provisioned_product_catalog(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_CandidateCatalog]:
    """正式S3の権限を先取りせず候補17資産を検査する。"""
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner_dsn,
        admin_dsn,
    ):
        with psycopg.connect(admin_dsn) as applicator:
            apply_product_authz_before_rule_placement(applicator)
            with psycopg.connect(admin_dsn) as observer:
                yield _CandidateCatalog(owner_dsn, applicator, observer)


def test_stage_a_split_function_asset_preserves_fixed_sql() -> None:
    """分割関数資産のSQL本体は承認済み候補と一致する。"""
    identity = "FUNCTION:public:resolve_stage_a_rule(uuid, text, text, boolean)"
    body = (_FUNCTION_ASSETS / "functions" / f"{identity}.sql").read_text()
    assert body.startswith(f"-- ELEMENT-TYPE: function\n-- ELEMENT-ID: {identity}\n")
    fixed_sql = _FUNCTION.read_text().split("CREATE OR REPLACE FUNCTION ", 1)[1]
    implementation = body.split("CREATE OR REPLACE FUNCTION ", 1)[1]
    assert implementation.startswith(fixed_sql)
    assert implementation[len(fixed_sql) :].startswith(
        "\nALTER FUNCTION public.resolve_stage_a_rule"
    )
    assert body.count("ALTER FUNCTION public.resolve_stage_a_rule") == 1
    assert body.count("REVOKE ALL PRIVILEGES ON FUNCTION") == 1
    assert body.count("GRANT EXECUTE ON FUNCTION") == 1
    assert body.rstrip().endswith("    TO pitchlog_app;")
    assert body.count("DO $authz$") == 1


def test_stage_a_split_acl_assets_are_exact() -> None:
    """追加列ACL資産は承認された15列・3更新列だけに閉じる。"""
    directory = _FUNCTION_ASSETS / "column_acl_expectations"
    files = tuple(directory.glob("*pitchlog_rule_resolution_fn_owner.sql"))
    assert len(files) == 15
    grants = tuple(
        line
        for path in files
        for line in path.read_text().splitlines()
        if line.startswith("GRANT ")
    )
    assert len(grants) == 18
    updates = {line for line in grants if line.startswith("GRANT UPDATE ")}
    assert updates == {
        "GRANT UPDATE (disabled) ON TABLE public.tenant_vocabularies "
        "TO pitchlog_rule_resolution_fn_owner;",
        "GRANT UPDATE (game_type_category) ON TABLE "
        "public.game_type_rule_defaults TO pitchlog_rule_resolution_fn_owner;",
        "GRANT UPDATE (id) ON TABLE public.rule_sets "
        "TO pitchlog_rule_resolution_fn_owner;",
    }
    assert len([line for line in grants if line.startswith("GRANT SELECT ")]) == 15


def test_stage_a_split_assets_execute_with_required_privileges(
    provisioned_product_catalog: _CandidateCatalog,
) -> None:
    """分割資産を隔離DBに適用し固定関数の権限境界を確かめる。"""
    catalog = provisioned_product_catalog
    _apply_candidate(catalog)
    role_asset = _FUNCTION_ASSETS / "roles/pitchlog_rule_resolution_fn_owner.sql"
    acl_assets = sorted(
        (_FUNCTION_ASSETS / "column_acl_expectations").glob(
            "*pitchlog_rule_resolution_fn_owner.sql"
        )
    )
    identity = "FUNCTION:public:resolve_stage_a_rule(uuid, text, text, boolean)"
    function_asset = _FUNCTION_ASSETS / "functions" / f"{identity}.sql"
    tenant_id = uuid4()
    with catalog.applicator.cursor() as cursor:
        cursor.execute(sql.SQL(cast(LiteralString, role_asset.read_text())))
        # shared public schema 資産への正式grantは所有解除後に追加する。
        cursor.execute(
            "GRANT USAGE ON SCHEMA public TO pitchlog_rule_resolution_fn_owner"
        )
        for asset in acl_assets:
            cursor.execute(sql.SQL(cast(LiteralString, asset.read_text())))
        cursor.execute(sql.SQL(cast(LiteralString, function_asset.read_text())))
        cursor.execute(
            "INSERT INTO public.tenants(id,name) VALUES (%s,%s)",
            (tenant_id, f"team-{tenant_id.hex[:12]}"),
        )
        cursor.execute(
            "INSERT INTO public.tenant_vocabularies "
            "(tenant_id,key,category,display_name) "
            "VALUES (%s,'tournament-a','tournament','大会A')",
            (tenant_id,),
        )
    catalog.applicator.commit()
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            "SELECT rolcanlogin, rolbypassrls, rolinherit, rolsuper "
            "FROM pg_catalog.pg_roles "
            "WHERE rolname = 'pitchlog_rule_resolution_fn_owner'"
        )
        assert cursor.fetchone() == (False, True, False, False)
        cursor.execute(
            "SELECT pg_catalog.has_function_privilege("
            "'pitchlog_app', "
            "'public.resolve_stage_a_rule(uuid,text,text,boolean)', 'EXECUTE'), "
            "pg_catalog.has_function_privilege("
            "'pitchlog_owner', "
            "'public.resolve_stage_a_rule(uuid,text,text,boolean)', 'EXECUTE')"
        )
        assert cursor.fetchone() == (True, False)
    catalog.observer.rollback()
    with catalog.applicator.cursor() as cursor:
        cursor.execute("SET ROLE pitchlog_app")
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),)
        )
        cursor.execute(
            "SELECT public.resolve_stage_a_rule(%s,%s,%s,%s)",
            (tenant_id, "game_official", "tournament-a", False),
        )
        result = cursor.fetchone()
        assert result is not None and result[0]["status"] == "resolved"
    catalog.applicator.rollback()


def test_stage_a_owner_asset_rejects_existing_membership(
    provisioned_product_catalog: _CandidateCatalog,
) -> None:
    """既存ownerにmembershipがあればBYPASSRLS付与前に停止する。"""
    catalog = provisioned_product_catalog
    asset = (
        _FUNCTION_ASSETS / "roles/pitchlog_rule_resolution_fn_owner.sql"
    ).read_text()
    with catalog.applicator.cursor() as cursor:
        cursor.execute("GRANT pitchlog_rule_resolution_fn_owner TO pitchlog_owner")
    catalog.applicator.commit()
    with pytest.raises(psycopg.errors.RaiseException, match="role collision"):
        with catalog.applicator.cursor() as cursor:
            cursor.execute(sql.SQL(cast(LiteralString, asset)))
    catalog.applicator.rollback()
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            "SELECT rolbypassrls FROM pg_catalog.pg_roles "
            "WHERE rolname = 'pitchlog_rule_resolution_fn_owner'"
        )
        assert cursor.fetchone() == (True,)
    catalog.observer.rollback()


def test_stage_a_function_asset_rejects_existing_extra_execute(
    provisioned_product_catalog: _CandidateCatalog,
) -> None:
    """既存関数の余剰EXECUTEが残る再適用を停止する。"""
    catalog = provisioned_product_catalog
    role_asset = (
        _FUNCTION_ASSETS / "roles/pitchlog_rule_resolution_fn_owner.sql"
    ).read_text()
    identity = "FUNCTION:public:resolve_stage_a_rule(uuid, text, text, boolean)"
    function_asset = (_FUNCTION_ASSETS / "functions" / f"{identity}.sql").read_text()
    with catalog.applicator.cursor() as cursor:
        cursor.execute(sql.SQL(cast(LiteralString, role_asset)))
        cursor.execute(
            "CREATE FUNCTION public.resolve_stage_a_rule(uuid,text,text,boolean) "
            "RETURNS jsonb LANGUAGE sql AS 'SELECT ''{}''::jsonb'"
        )
        cursor.execute(
            "ALTER FUNCTION public.resolve_stage_a_rule(uuid,text,text,boolean) "
            "OWNER TO pitchlog_rule_resolution_fn_owner"
        )
        cursor.execute(
            "REVOKE ALL PRIVILEGES ON FUNCTION "
            "public.resolve_stage_a_rule(uuid,text,text,boolean) FROM PUBLIC"
        )
        cursor.execute(
            "GRANT EXECUTE ON FUNCTION "
            "public.resolve_stage_a_rule(uuid,text,text,boolean) TO pitchlog_app"
        )
        cursor.execute(
            "GRANT EXECUTE ON FUNCTION "
            "public.resolve_stage_a_rule(uuid,text,text,boolean) TO pitchlog_owner"
        )
    catalog.applicator.commit()
    with pytest.raises(psycopg.errors.RaiseException, match="function collision"):
        with catalog.applicator.cursor() as cursor:
            cursor.execute(sql.SQL(cast(LiteralString, function_asset)))
    catalog.applicator.rollback()


def test_stage_a_function_asset_reapplies_with_exact_acl(
    provisioned_product_catalog: _CandidateCatalog,
) -> None:
    """期待ownerとEXECUTEだけを持つ既存関数は再適用できる。"""
    catalog = provisioned_product_catalog
    role_asset = (
        _FUNCTION_ASSETS / "roles/pitchlog_rule_resolution_fn_owner.sql"
    ).read_text()
    identity = "FUNCTION:public:resolve_stage_a_rule(uuid, text, text, boolean)"
    function_asset = (_FUNCTION_ASSETS / "functions" / f"{identity}.sql").read_text()
    with catalog.applicator.cursor() as cursor:
        cursor.execute(sql.SQL(cast(LiteralString, role_asset)))
        cursor.execute(sql.SQL(cast(LiteralString, function_asset)))
    catalog.applicator.commit()
    with catalog.applicator.cursor() as cursor:
        cursor.execute(sql.SQL(cast(LiteralString, role_asset)))
        cursor.execute(sql.SQL(cast(LiteralString, function_asset)))
    catalog.applicator.rollback()


def _owner_url(dsn: str) -> URL:
    """隔離fixtureのowner接続をSQLAlchemyに渡す。"""
    parts = conninfo_to_dict(dsn)
    assert all(parts.get(key) is not None for key in ("user", "host", "port", "dbname"))
    return URL.create(
        "postgresql+psycopg",
        username=str(parts["user"]),
        password=None if parts.get("password") is None else str(parts["password"]),
        host=str(parts["host"]),
        port=int(str(parts["port"])),
        database=str(parts["dbname"]),
    )


def _apply_candidate_owner(owner_dsn: str) -> None:
    """正式Alembic headを動かさず候補upgradeだけを実行する。"""
    upgrade = runpy.run_path(str(_CANDIDATE))["upgrade"]
    engine = create_engine(_owner_url(owner_dsn))
    try:
        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                upgrade()
    finally:
        engine.dispose()


def _apply_candidate(catalog: _CandidateCatalog) -> None:
    """既存製品認可済みfixtureへ未登録候補を適用する。"""
    _apply_candidate_owner(catalog.owner_dsn)


@contextmanager
def _fresh_schema_database(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[str, str]]:
    """空DBから現行Alembic headまで起動し、認可前で渡す。"""
    with disposable_postgres_cluster() as cluster:
        _require_historical_cluster(cluster)
        owner_password = secrets.token_urlsafe(24)
        product_database = "pitchlog_stage_a_candidate"
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            assert admin.info.dbname == "pitchlog_disposable"
            with admin.cursor() as cursor:
                # factoryが所有を証明したseed DBだけを閉じる。
                cursor.execute(
                    sql.SQL(
                        "REVOKE CONNECT, TEMPORARY ON DATABASE {} FROM PUBLIC"
                    ).format(sql.Identifier(admin.info.dbname))
                )
                cursor.execute(
                    sql.SQL(
                        "CREATE ROLE pitchlog_owner WITH NOSUPERUSER NOBYPASSRLS "
                        "LOGIN NOCREATEROLE NOCREATEDB NOREPLICATION NOINHERIT "
                        "PASSWORD {}"
                    ).format(sql.Literal(owner_password))
                )
                cursor.execute(
                    sql.SQL("CREATE DATABASE {} OWNER pitchlog_owner").format(
                        sql.Identifier(product_database)
                    )
                )
        admin_dsn = make_conninfo(cluster.admin_dsn, dbname=product_database)
        owner_dsn = make_conninfo(
            cluster.role_dsn_template,
            dbname=product_database,
            user="pitchlog_owner",
            password=owner_password,
        )
        monkeypatch.setenv(
            "PITCHLOG_MIGRATION_DATABASE_URL",
            _owner_url(owner_dsn).render_as_string(hide_password=False),
        )
        command.upgrade(
            Config(str(_BACKEND_ROOT / "alembic.ini")), "0033_game_rules_immutable"
        )
        yield owner_dsn, admin_dsn


def test_formal_stage_a_startup_preserves_closed_publication(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """実revision・製品認可をS0→S3で確定しても公開は拒否する。"""
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner_dsn,
        admin_dsn,
    ):
        result = advance_stage_a_from_s0(owner_dsn=owner_dsn, applicator_dsn=admin_dsn)
        assert result.completed_stage == "S3"
        assert result.publishable is False
        with psycopg.connect(admin_dsn) as admin, admin.cursor() as cursor:
            cursor.execute("SELECT version_num FROM public.alembic_version")
            assert cursor.fetchone() == ("0036_initial_right_storage",)
            cursor.execute("SELECT count(*) FROM public.game_type_rule_defaults")
            assert cursor.fetchone() == (5,)
            cursor.execute(
                "SELECT pg_catalog.has_function_privilege("
                "'pitchlog_app', "
                "'public.resolve_stage_a_rule(uuid,text,text,boolean)', 'EXECUTE')"
            )
            assert cursor.fetchone() == (True,)
        with pytest.raises(StageAStartupError, match="revision"):
            advance_stage_a_from_s0(owner_dsn=owner_dsn, applicator_dsn=admin_dsn)
        resumed = resume_stage_a_after_placement(
            owner_dsn=owner_dsn, applicator_dsn=admin_dsn
        )
        assert resumed.publishable is False


def test_formal_stage_a_startup_rechecks_committed_s1(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S1が確定済みでも再適用は閉鎖状態でS3へ進める。"""
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner_dsn,
        admin_dsn,
    ):
        with psycopg.connect(admin_dsn) as applicator:
            apply_product_authz_before_rule_placement(applicator)
        result = advance_stage_a_from_s0(owner_dsn=owner_dsn, applicator_dsn=admin_dsn)
        assert result.completed_stage == "S3"
        assert result.publishable is False


def test_formal_stage_a_migration_rejects_unstaged_upgrade(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """認可前の直接Alembic headでは配置もrevisionも確定しない。"""
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner_dsn,
        _,
    ):
        with pytest.raises(RuntimeError, match="FORCE RLS"):
            command.upgrade(Config(str(_BACKEND_ROOT / "alembic.ini")), "head")
        with psycopg.connect(owner_dsn) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT version_num FROM public.alembic_version")
            assert cursor.fetchone() == ("0033_game_rules_immutable",)
            cursor.execute("SELECT count(*) FROM public.game_type_rule_defaults")
            assert cursor.fetchone() == (0,)


def test_formal_stage_a_startup_authz_failure_keeps_placement_closed(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S2確定後のS3失敗では配置を残し関数を公開しない。"""
    import pitchlog.db.stage_a_startup as startup

    original_apply = startup.apply_product_authz_ddl

    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner_dsn,
        admin_dsn,
    ):

        def fail_authz(_connection: object) -> None:
            raise RuntimeError("S3故障注入")

        monkeypatch.setattr(startup, "apply_product_authz_ddl", fail_authz)
        with pytest.raises(RuntimeError, match="S3故障注入"):
            startup.advance_stage_a_from_s0(
                owner_dsn=owner_dsn, applicator_dsn=admin_dsn
            )
        with psycopg.connect(admin_dsn) as admin, admin.cursor() as cursor:
            cursor.execute("SELECT version_num FROM public.alembic_version")
            assert cursor.fetchone() == ("0036_initial_right_storage",)
            cursor.execute("SELECT count(*) FROM public.game_type_rule_defaults")
            assert cursor.fetchone() == (5,)
            cursor.execute(
                "SELECT pg_catalog.to_regprocedure("
                "'public.resolve_stage_a_rule(uuid,text,text,boolean)')"
            )
            assert cursor.fetchone() == (None,)
        monkeypatch.setattr(startup, "apply_product_authz_ddl", original_apply)
        resumed = resume_stage_a_after_placement(
            owner_dsn=owner_dsn, applicator_dsn=admin_dsn
        )
        assert resumed.completed_stage == "S3"
        assert resumed.publishable is False


def test_formal_stage_a_resume_rejects_changed_seed(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S2後に規則値が改変された場合は認可Bを再開しない。"""
    import pitchlog.db.stage_a_startup as startup

    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner_dsn,
        admin_dsn,
    ):

        def fail_authz(_connection: object) -> None:
            raise RuntimeError("S3故障注入")

        monkeypatch.setattr(startup, "apply_product_authz_ddl", fail_authz)
        with pytest.raises(RuntimeError, match="S3故障注入"):
            startup.advance_stage_a_from_s0(
                owner_dsn=owner_dsn, applicator_dsn=admin_dsn
            )
        with psycopg.connect(admin_dsn) as admin, admin.cursor() as cursor:
            cursor.execute(
                "UPDATE public.rule_sets SET extra_innings_limit = 13 WHERE id = %s",
                (_OFFICIAL_ID,),
            )
        with pytest.raises(StageAStartupError, match="固定規則5行"):
            resume_stage_a_after_placement(
                owner_dsn=owner_dsn, applicator_dsn=admin_dsn
            )


def test_stage_a_candidate_entry_stops_before_publication(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S0からS3へ順に進めても候補入口は公開を許可しない。"""
    entry = runpy.run_path(str(_STARTUP))
    advance = entry["advance_stage_a_candidate_from_s0"]
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner_dsn,
        admin_dsn,
    ):
        result = advance(owner_dsn=owner_dsn, applicator_dsn=admin_dsn)
        assert result.completed_stage == "S3"
        assert result.publishable is False
        with psycopg.connect(admin_dsn) as admin:
            with admin.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM public.game_type_rule_defaults")
                assert cursor.fetchone() == (5,)
                cursor.execute(
                    "SELECT to_regprocedure("
                    "'public.resolve_stage_a_rule(uuid,text,text,boolean)')"
                )
                function_row = cursor.fetchone()
                assert function_row is not None and function_row[0] is not None
            admin.rollback()
        with pytest.raises(RuntimeError, match="S0は認可適用前"):
            advance(owner_dsn=owner_dsn, applicator_dsn=admin_dsn)


def test_stage_a_candidate_entry_keeps_placement_after_s3_failure(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S3衝突時はA配置を保持して関数公開を止める。"""
    entry = runpy.run_path(str(_STARTUP))
    advance = entry["advance_stage_a_candidate_from_s0"]

    def fail_s3(*_args: object) -> None:
        raise RuntimeError("S3故障注入")

    advance.__globals__["_apply_candidate_authz"] = fail_s3
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner_dsn,
        admin_dsn,
    ):
        with pytest.raises(RuntimeError, match="S3故障注入"):
            advance(owner_dsn=owner_dsn, applicator_dsn=admin_dsn)
        with psycopg.connect(admin_dsn) as admin:
            with admin.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM public.game_type_rule_defaults")
                assert cursor.fetchone() == (5,)
                cursor.execute(
                    "SELECT to_regprocedure("
                    "'public.resolve_stage_a_rule(uuid,text,text,boolean)')"
                )
                assert cursor.fetchone() == (None,)
            admin.rollback()


def test_stage_a_candidate_entry_rejects_other_database(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ownerと管理接続が別DBならS1前に停止する。"""
    advance = runpy.run_path(str(_STARTUP))["advance_stage_a_candidate_from_s0"]
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner_dsn,
        admin_dsn,
    ):
        other_dsn = make_conninfo(admin_dsn, dbname="postgres")
        with pytest.raises(RuntimeError, match="接続先が一致しません"):
            advance(owner_dsn=owner_dsn, applicator_dsn=other_dsn)
        with psycopg.connect(admin_dsn) as admin:
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT relforcerowsecurity FROM pg_catalog.pg_class "
                    "WHERE oid = 'public.rule_sets'::regclass"
                )
                assert cursor.fetchone() == (False,)
            admin.rollback()


def test_stage_a_candidate_entry_rejects_modified_asset_before_s1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """17件のままSQLを変えても候補入口は適用前に停止する。"""
    entry = runpy.run_path(str(_STARTUP))
    advance = entry["advance_stage_a_candidate_from_s0"]
    copied = tmp_path / "tsk550_authz"
    shutil.copytree(_FUNCTION_ASSETS, copied)
    role_asset = copied / "roles/pitchlog_rule_resolution_fn_owner.sql"
    role_asset.write_text(role_asset.read_text() + "\nSELECT 1;\n")
    monkeypatch.setitem(advance.__globals__, "_AUTHZ", copied)
    with pytest.raises(RuntimeError, match="集合または内容が不一致"):
        advance(owner_dsn="invalid", applicator_dsn="invalid")


def _seed_state(catalog: _CandidateCatalog) -> tuple[int, int, int]:
    """隔離DB上の候補行数と一時policy数を観測する。"""
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM public.rule_sets WHERE id = ANY(%s)",
            (
                [
                    str(_OFFICIAL_ID),
                    "8fa3b9b7-481b-538b-8093-6af96050d97f",
                    "b679f9f1-86a8-54f7-9466-a5b01d932953",
                    "45677369-9e25-5220-9a30-1d89b338174c",
                    "6ff51660-bee2-552a-9075-1f3f3d1e0dd7",
                ],
            ),
        )
        rule_row = cursor.fetchone()
        assert rule_row is not None
        rule_count = rule_row[0]
        cursor.execute(
            "SELECT count(*) FROM public.game_type_rule_defaults "
            "WHERE game_type_key = ANY(%s)",
            (
                [
                    "game_official",
                    "game_semi_official",
                    "game_open",
                    "game_intrasquad",
                    "game_other",
                ],
            ),
        )
        default_row = cursor.fetchone()
        assert default_row is not None
        default_count = default_row[0]
        cursor.execute(
            "SELECT count(*) FROM pg_catalog.pg_policies "
            "WHERE schemaname = 'public' AND policyname LIKE 'tsk550_seed_%'"
        )
        policy_row = cursor.fetchone()
        assert policy_row is not None
        policy_count = policy_row[0]
    catalog.observer.rollback()
    return rule_count, default_count, policy_count


def test_stage_a_staged_startup_from_empty_database_and_retry(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空DBからschema・認可・配置を段階実行し故障後の停止を確かめる。"""
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner_dsn,
        admin_dsn,
    ):
        with pytest.raises(RuntimeError, match="FORCE RLS"):
            _apply_candidate_owner(owner_dsn)
        with psycopg.connect(admin_dsn) as admin:
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT relforcerowsecurity FROM pg_catalog.pg_class "
                    "WHERE oid = 'public.rule_sets'::regclass"
                )
                assert cursor.fetchone() == (False,)
            admin.rollback()
            apply_product_authz_before_rule_placement(admin)
            with admin.cursor() as cursor:
                cursor.execute(
                    "CREATE FUNCTION public.tsk550_candidate_fail() "
                    "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
                    "RAISE EXCEPTION 'injected default failure'; END $$"
                )
                cursor.execute(
                    "CREATE TRIGGER tsk550_candidate_fail BEFORE INSERT "
                    "ON public.game_type_rule_defaults FOR EACH ROW "
                    "EXECUTE FUNCTION public.tsk550_candidate_fail()"
                )
            admin.commit()
            with pytest.raises(Exception, match="injected default failure"):
                _apply_candidate_owner(owner_dsn)
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) FROM public.rule_sets WHERE id = %s",
                    (_OFFICIAL_ID,),
                )
                assert cursor.fetchone() == (0,)
                cursor.execute(
                    "SELECT count(*) FROM pg_catalog.pg_policies "
                    "WHERE policyname LIKE 'tsk550_seed_%'"
                )
                assert cursor.fetchone() == (0,)
                cursor.execute(
                    "DROP TRIGGER tsk550_candidate_fail "
                    "ON public.game_type_rule_defaults"
                )
                cursor.execute("DROP FUNCTION public.tsk550_candidate_fail()")
            admin.commit()
            _apply_candidate_owner(owner_dsn)
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) FROM public.rule_sets WHERE id = %s",
                    (_OFFICIAL_ID,),
                )
                assert cursor.fetchone() == (1,)
                cursor.execute("SELECT count(*) FROM public.game_type_rule_defaults")
                assert cursor.fetchone() == (5,)
            admin.rollback()
            with pytest.raises(RuntimeError, match="衝突"):
                _apply_candidate_owner(owner_dsn)
            # 未登録候補の再実行は停止する。正式revisionのskipは後続ゲートで検証する。
            with admin.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM public.game_type_rule_defaults")
                assert cursor.fetchone() == (5,)
                cursor.execute(
                    "SELECT to_regprocedure("
                    "'public.resolve_stage_a_rule(uuid,text,text,boolean)')"
                )
                assert cursor.fetchone() == (None,)
            admin.rollback()


def test_stage_a_candidate_places_five_pairs_without_persistent_policy(
    provisioned_product_catalog: _CandidateCatalog,
) -> None:
    """候補は5組を置き一時RLSを残さない。"""
    catalog = provisioned_product_catalog
    _apply_candidate(catalog)
    assert _seed_state(catalog) == (5, 5, 0)


def test_stage_a_candidate_rejects_existing_id_without_mutation(
    provisioned_product_catalog: _CandidateCatalog,
) -> None:
    """値が同じ既存IDも採用せず、候補全体を取り消す。"""
    catalog = provisioned_product_catalog
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO public.rule_sets "
            "(id, regulation_innings, called_game_conditions, "
            "extra_innings_limit, tiebreak_rule, uses_dh) "
            "VALUES (%s, 9, '[]'::jsonb, 12, NULL, true)",
            (_OFFICIAL_ID,),
        )
    catalog.applicator.commit()
    with pytest.raises(RuntimeError, match="衝突"):
        _apply_candidate(catalog)
    assert _seed_state(catalog) == (1, 0, 0)


def test_stage_a_candidate_rejects_existing_key_without_mutation(
    provisioned_product_catalog: _CandidateCatalog,
) -> None:
    """既存の区分キーも流用せず、候補全体を取り消す。"""
    catalog = provisioned_product_catalog
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO public.rule_sets "
            "(id, regulation_innings, called_game_conditions, "
            "extra_innings_limit, tiebreak_rule, uses_dh) "
            "VALUES (%s, 9, '[]'::jsonb, 9, NULL, true)",
            (uuid4(),),
        )
        cursor.execute(
            "INSERT INTO public.game_type_rule_defaults "
            "(game_type_key, game_type_category, rule_set_id) "
            "SELECT 'game_other', 'game_type', id FROM public.rule_sets "
            "WHERE id <> %s LIMIT 1",
            (_OFFICIAL_ID,),
        )
    catalog.applicator.commit()
    with pytest.raises(RuntimeError, match="衝突"):
        _apply_candidate(catalog)
    assert _seed_state(catalog) == (0, 1, 0)


def test_stage_a_candidate_preserves_unrelated_existing_rule(
    provisioned_product_catalog: _CandidateCatalog,
) -> None:
    """認可済み既存DBへの追随で対象外行を変更しない。"""
    catalog = provisioned_product_catalog
    existing_id = uuid4()
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO public.rule_sets "
            "(id, regulation_innings, called_game_conditions, "
            "extra_innings_limit, tiebreak_rule, uses_dh) "
            "VALUES (%s, 7, '[]'::jsonb, 8, NULL, false)",
            (existing_id,),
        )
    catalog.applicator.commit()
    _apply_candidate(catalog)
    assert _seed_state(catalog) == (5, 5, 0)
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            "SELECT regulation_innings, called_game_conditions, "
            "extra_innings_limit, tiebreak_rule, uses_dh "
            "FROM public.rule_sets WHERE id = %s",
            (existing_id,),
        )
        assert cursor.fetchone() == (7, [], 8, None, False)
    catalog.observer.rollback()


def test_stage_a_candidate_insert_fault_rolls_back_everything(
    provisioned_product_catalog: _CandidateCatalog,
) -> None:
    """規則行の後で既定行が失敗しても5組と一時RLSを残さない。"""
    catalog = provisioned_product_catalog
    with catalog.applicator.cursor() as cursor:
        cursor.execute("""
            CREATE FUNCTION public.tsk550_candidate_fail() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
                RAISE EXCEPTION 'injected default failure';
            END $$
        """)
        cursor.execute("""
            CREATE TRIGGER tsk550_candidate_fail
            BEFORE INSERT ON public.game_type_rule_defaults
            FOR EACH ROW EXECUTE FUNCTION public.tsk550_candidate_fail()
        """)
    catalog.applicator.commit()
    with pytest.raises(Exception, match="injected default failure"):
        _apply_candidate(catalog)
    assert _seed_state(catalog) == (0, 0, 0)


def test_stage_a_candidate_keeps_seed_when_authz_transaction_fails(
    provisioned_product_catalog: _CandidateCatalog,
) -> None:
    """配置成功後の認可候補取消しで作成入口を公開しない。"""
    catalog = provisioned_product_catalog
    _apply_candidate(catalog)
    with pytest.raises(RuntimeError, match="injected authz failure"):
        with catalog.applicator.cursor() as cursor:
            cursor.execute(
                "CREATE FUNCTION public.tsk550_authz_failure_probe() "
                "RETURNS boolean LANGUAGE sql AS 'SELECT true'"
            )
            raise RuntimeError("injected authz failure")
    catalog.applicator.rollback()
    assert _seed_state(catalog) == (5, 5, 0)
    with catalog.observer.cursor() as cursor:
        cursor.execute("SELECT to_regprocedure('public.tsk550_authz_failure_probe()')")
        assert cursor.fetchone() == (None,)
        cursor.execute(
            "SELECT to_regprocedure("
            "'public.resolve_stage_a_rule(uuid,text,text,boolean)')"
        )
        assert cursor.fetchone() == (None,)
    catalog.observer.rollback()
    candidate = runpy.run_path(str(_STARTUP))
    assets = candidate["_require_candidate_assets"]()
    candidate["_apply_candidate_authz"](catalog.applicator, assets.authz)
    assert _seed_state(catalog) == (5, 5, 0)


def _install_candidate_function(catalog: _CandidateCatalog) -> UUID:
    """隔離DBだけに候補関数と専用ownerを置く。"""
    tenant_id = uuid4()
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "GRANT USAGE ON SCHEMA public TO pitchlog_rule_resolution_fn_owner"
        )
        cursor.execute(
            "GRANT SELECT (tenant_id, key, category, disabled), "
            "UPDATE (disabled) ON public.tenant_vocabularies "
            "TO pitchlog_rule_resolution_fn_owner"
        )
        cursor.execute(
            "GRANT SELECT (tenant_id, tournament_key) "
            "ON public.tournament_rule_assignments "
            "TO pitchlog_rule_resolution_fn_owner"
        )
        cursor.execute(
            "GRANT SELECT (game_type_key, game_type_category, rule_set_id) "
            "ON public.game_type_rule_defaults TO pitchlog_rule_resolution_fn_owner"
        )
        cursor.execute(
            "GRANT UPDATE(game_type_category) "
            "ON public.game_type_rule_defaults "
            "TO pitchlog_rule_resolution_fn_owner"
        )
        cursor.execute(
            "GRANT SELECT (id, regulation_innings, called_game_conditions, "
            "extra_innings_limit, tiebreak_rule, uses_dh) "
            "ON public.rule_sets TO pitchlog_rule_resolution_fn_owner"
        )
        cursor.execute(
            "GRANT UPDATE(id) ON public.rule_sets TO pitchlog_rule_resolution_fn_owner"
        )
        cursor.execute(sql.SQL(cast(LiteralString, _FUNCTION.read_text())))
        cursor.execute(
            "ALTER FUNCTION public.resolve_stage_a_rule(uuid,text,text,boolean) "
            "OWNER TO pitchlog_rule_resolution_fn_owner"
        )
        cursor.execute(
            "REVOKE ALL ON FUNCTION "
            "public.resolve_stage_a_rule(uuid,text,text,boolean) FROM PUBLIC"
        )
        cursor.execute(
            "GRANT EXECUTE ON FUNCTION "
            "public.resolve_stage_a_rule(uuid,text,text,boolean) TO pitchlog_app"
        )
        cursor.execute(
            "INSERT INTO public.tenants(id,name) VALUES (%s,%s)",
            (tenant_id, f"team-{tenant_id.hex[:12]}"),
        )
        cursor.execute(
            "INSERT INTO public.tenant_vocabularies "
            "(tenant_id,key,category,display_name) "
            "VALUES (%s,'tournament-a','tournament','大会A')",
            (tenant_id,),
        )
    catalog.applicator.commit()
    return tenant_id


def test_stage_a_privileged_table_lock_waits_for_resolver_transaction(
    provisioned_product_catalog: _CandidateCatalog,
) -> None:
    """特権変更の排他表ロックは進行中の解決読取を越えない。"""
    catalog = provisioned_product_catalog
    _apply_candidate(catalog)
    with catalog.applicator.cursor() as cursor:
        cursor.execute("SELECT id FROM public.rule_sets WHERE id = %s", (_OFFICIAL_ID,))
        assert cursor.fetchone() == (_OFFICIAL_ID,)
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            "UPDATE public.rule_sets SET extra_innings_limit = 10 WHERE id = %s",
            (_OFFICIAL_ID,),
        )
        assert cursor.rowcount == 1
    catalog.observer.rollback()
    catalog.applicator.rollback()
    tenant_id = _install_candidate_function(catalog)
    with catalog.applicator.cursor() as cursor:
        cursor.execute("SET ROLE pitchlog_app")
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),)
        )
        cursor.execute(
            "SELECT public.resolve_stage_a_rule(%s,%s,%s,%s)",
            (tenant_id, "game_official", "tournament-a", False),
        )
        result = cursor.fetchone()
        assert result is not None and result[0]["status"] == "resolved"
    with pytest.raises(psycopg.errors.LockNotAvailable):
        with catalog.observer.cursor() as cursor:
            cursor.execute("SET lock_timeout = '250ms'")
            cursor.execute(
                "LOCK TABLE public.rule_sets, public.game_type_rule_defaults "
                "IN ACCESS EXCLUSIVE MODE"
            )
    catalog.observer.rollback()
    with pytest.raises(psycopg.errors.LockNotAvailable):
        with catalog.observer.cursor() as cursor:
            cursor.execute("SET lock_timeout = '250ms'")
            cursor.execute(
                "UPDATE public.rule_sets SET extra_innings_limit = 10 WHERE id = %s",
                (_OFFICIAL_ID,),
            )
    catalog.observer.rollback()
    catalog.applicator.rollback()
    with catalog.observer.cursor() as cursor:
        cursor.execute(
            "LOCK TABLE public.rule_sets, public.game_type_rule_defaults "
            "IN ACCESS EXCLUSIVE MODE NOWAIT"
        )
        cursor.execute(
            "UPDATE public.rule_sets SET extra_innings_limit = 10 WHERE id = %s",
            (_OFFICIAL_ID,),
        )
    catalog.observer.commit()
    with catalog.applicator.cursor() as cursor:
        cursor.execute("SET ROLE pitchlog_app")
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),)
        )
        cursor.execute(
            "SELECT public.resolve_stage_a_rule(%s,%s,%s,%s)",
            (tenant_id, "game_official", "tournament-a", False),
        )
        invalid = cursor.fetchone()
        assert invalid is not None and invalid[0] == {"status": "invalid_rule"}
    catalog.applicator.rollback()


def test_stage_a_for_share_requires_write_capability(
    provisioned_product_catalog: _CandidateCatalog,
) -> None:
    """FOR SHARE案に必要な列UPDATEが実書込能力になることを示す。"""
    catalog = provisioned_product_catalog
    _apply_candidate(catalog)
    _install_candidate_function(catalog)
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "REVOKE UPDATE(game_type_category) "
            "ON public.game_type_rule_defaults "
            "FROM pitchlog_rule_resolution_fn_owner"
        )
        cursor.execute(
            "REVOKE UPDATE(id) ON public.rule_sets "
            "FROM pitchlog_rule_resolution_fn_owner"
        )
        cursor.execute("SET ROLE pitchlog_rule_resolution_fn_owner")
        cursor.execute("SAVEPOINT no_update_grant")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(
                "SELECT rule_set_id FROM public.game_type_rule_defaults "
                "WHERE game_type_key = 'game_official' FOR SHARE"
            )
        cursor.execute("ROLLBACK TO SAVEPOINT no_update_grant")
        cursor.execute("SAVEPOINT no_rule_update_grant")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(
                "SELECT id FROM public.rule_sets WHERE id = %s FOR SHARE",
                (_OFFICIAL_ID,),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT no_rule_update_grant")
        cursor.execute("RESET ROLE")
        cursor.execute(
            "GRANT UPDATE(game_type_category) ON public.game_type_rule_defaults "
            "TO pitchlog_rule_resolution_fn_owner"
        )
        cursor.execute(
            "GRANT UPDATE(id) ON public.rule_sets TO pitchlog_rule_resolution_fn_owner"
        )
        cursor.execute("SET ROLE pitchlog_rule_resolution_fn_owner")
        cursor.execute(
            "SELECT rule_set_id FROM public.game_type_rule_defaults "
            "WHERE game_type_key = 'game_official' FOR SHARE"
        )
        assert cursor.fetchone() == (_OFFICIAL_ID,)
        cursor.execute(
            "SELECT id FROM public.rule_sets WHERE id = %s FOR SHARE",
            (_OFFICIAL_ID,),
        )
        assert cursor.fetchone() == (_OFFICIAL_ID,)
        cursor.execute(
            "UPDATE public.game_type_rule_defaults "
            "SET game_type_category = game_type_category "
            "WHERE game_type_key = 'game_official'"
        )
        assert cursor.rowcount == 1
        cursor.execute("RESET ROLE")
    catalog.applicator.rollback()


def test_stage_a_candidate_grants_and_revokes_only_required_columns(
    provisioned_product_catalog: _CandidateCatalog,
) -> None:
    """候補ownerの3列UPDATEと関数EXECUTEを撤去まで照合する。"""
    catalog = provisioned_product_catalog
    _apply_candidate(catalog)
    tenant_id = _install_candidate_function(catalog)
    expected = {
        ("tenant_vocabularies", "disabled"),
        ("game_type_rule_defaults", "game_type_category"),
        ("rule_sets", "id"),
    }
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT table_name, column_name FROM information_schema.column_privileges "
            "WHERE grantee = 'pitchlog_rule_resolution_fn_owner' "
            "AND privilege_type = 'UPDATE'"
        )
        assert set(cursor.fetchall()) == expected
        cursor.execute(
            "SELECT pg_has_role('pitchlog_app', "
            "'pitchlog_rule_resolution_fn_owner', 'MEMBER')"
        )
        assert cursor.fetchone() == (False,)
        cursor.execute(
            "SELECT has_function_privilege('pitchlog_app', "
            "'public.resolve_stage_a_rule(uuid,text,text,boolean)', 'EXECUTE')"
        )
        assert cursor.fetchone() == (True,)
        cursor.execute(
            "REVOKE EXECUTE ON FUNCTION "
            "public.resolve_stage_a_rule(uuid,text,text,boolean) FROM pitchlog_app"
        )
        cursor.execute(
            "REVOKE UPDATE(disabled) ON public.tenant_vocabularies "
            "FROM pitchlog_rule_resolution_fn_owner"
        )
        cursor.execute(
            "REVOKE UPDATE(game_type_category) ON public.game_type_rule_defaults "
            "FROM pitchlog_rule_resolution_fn_owner"
        )
        cursor.execute(
            "REVOKE UPDATE(id) ON public.rule_sets "
            "FROM pitchlog_rule_resolution_fn_owner"
        )
        cursor.execute(
            "SELECT table_name, column_name FROM information_schema.column_privileges "
            "WHERE grantee = 'pitchlog_rule_resolution_fn_owner' "
            "AND privilege_type = 'UPDATE'"
        )
        assert cursor.fetchall() == []
        cursor.execute(
            "SELECT has_function_privilege('pitchlog_app', "
            "'public.resolve_stage_a_rule(uuid,text,text,boolean)', 'EXECUTE')"
        )
        assert cursor.fetchone() == (False,)
        cursor.execute("SET ROLE pitchlog_app")
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),)
        )
        cursor.execute("SAVEPOINT revoked_execute")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(
                "SELECT public.resolve_stage_a_rule(%s,%s,%s,%s)",
                (tenant_id, "game_official", "tournament-a", False),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT revoked_execute")
        cursor.execute("RESET ROLE")
    catalog.applicator.rollback()


def test_stage_a_function_candidate_rejects_override_and_guc_mismatch(
    provisioned_product_catalog: _CandidateCatalog,
) -> None:
    """未登録関数候補は第1UUIDとGUCの不一致等を拒否する。"""
    catalog = provisioned_product_catalog
    _apply_candidate(catalog)
    tenant_id = _install_candidate_function(catalog)
    other_tenant_id = uuid4()
    with catalog.applicator.cursor() as cursor:
        cursor.execute("SET ROLE pitchlog_app")
        for table in ("rule_sets", "tournament_rule_assignments"):
            cursor.execute("SAVEPOINT direct_select")
            with pytest.raises(Exception, match="permission denied"):
                cursor.execute(f"SELECT count(*) FROM public.{table}")
            cursor.execute("ROLLBACK TO SAVEPOINT direct_select")
            cursor.execute("RELEASE SAVEPOINT direct_select")
        cursor.execute(
            "SELECT public.resolve_stage_a_rule(%s,%s,%s,%s)",
            (tenant_id, "game_official", "tournament-a", False),
        )
        missing_guc = cursor.fetchone()
        assert missing_guc is not None
        assert missing_guc[0] == {"status": "rule_not_available"}
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),)
        )
        for game_type in (
            "game_official",
            "game_semi_official",
            "game_open",
            "game_intrasquad",
            "game_other",
        ):
            cursor.execute(
                "SELECT public.resolve_stage_a_rule(%s,%s,%s,%s)",
                (tenant_id, game_type, "tournament-a", False),
            )
            row = cursor.fetchone()
            assert row is not None and row[0]["status"] == "resolved"
            validate_correlations(decode_structure(row[0]["rule"]))
        cursor.execute(
            "SELECT public.resolve_stage_a_rule(%s,%s,%s,%s)",
            (tenant_id, "game_official", "tournament-a", True),
        )
        row = cursor.fetchone()
        assert row is not None and row[0] == {"status": "stage_a_unsupported"}
        cursor.execute(
            "SELECT public.resolve_stage_a_rule(%s,%s,%s,%s)",
            (other_tenant_id, "game_official", "tournament-a", False),
        )
        row = cursor.fetchone()
        assert row is not None and row[0] == {"status": "rule_not_available"}
        cursor.execute("RESET ROLE")
    catalog.applicator.rollback()

    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO public.tournament_rule_assignments "
            "(tenant_id,tournament_key,rule_set_id) VALUES (%s,%s,%s)",
            (tenant_id, "tournament-a", _OFFICIAL_ID),
        )
    catalog.applicator.commit()
    with catalog.applicator.cursor() as cursor:
        cursor.execute("SET ROLE pitchlog_app")
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),)
        )
        cursor.execute(
            "SELECT public.resolve_stage_a_rule(%s,%s,%s,%s)",
            (tenant_id, "game_official", "tournament-a", False),
        )
        row = cursor.fetchone()
        assert row is not None and row[0] == {"status": "stage_a_unsupported"}
        cursor.execute("RESET ROLE")
    catalog.applicator.rollback()


@dataclass(frozen=True, repr=False)
class _PublicResolverDatabase:
    """資格文字列をreprへ出さない正式S3の隔離接続情報。"""

    admin_dsn: str
    engine: Engine
    tenant_a: UUID
    tenant_b: UUID
    events: list[str]


@pytest.fixture
def public_resolver_database(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_PublicResolverDatabase]:
    """正式S3と実app接続を用意し、実scopeのengine factoryだけを接続する。"""
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner_dsn,
        admin_dsn,
    ):
        startup = advance_stage_a_from_s0(owner_dsn=owner_dsn, applicator_dsn=admin_dsn)
        assert startup.completed_stage == "S3"
        assert startup.publishable is False
        tenant_a, tenant_b = uuid4(), uuid4()
        password = secrets.token_urlsafe(24)
        with psycopg.connect(admin_dsn) as admin, admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("ALTER ROLE pitchlog_app PASSWORD {}").format(
                    sql.Literal(password)
                )
            )
            cursor.executemany(
                "INSERT INTO public.tenants(id,name) VALUES (%s,%s)",
                ((tenant_a, "resolver-team-a"), (tenant_b, "resolver-team-b")),
            )
            cursor.executemany(
                "INSERT INTO public.tenant_vocabularies "
                "(tenant_id,key,category,display_name,disabled) "
                "VALUES (%s,%s,'tournament',%s,%s)",
                (
                    (tenant_a, "tournament-a", "大会A", False),
                    (tenant_b, "tournament-b", "大会B", False),
                    (tenant_a, "disabled-a", "無効大会A", True),
                ),
            )
        app_dsn = make_conninfo(owner_dsn, user="pitchlog_app", password=password)
        app_url = _owner_url(app_dsn).update_query_dict({"sslmode": "disable"})
        monkeypatch.setenv(
            "PITCHLOG_DATABASE_URL", app_url.render_as_string(hide_password=False)
        )
        monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")
        with psycopg.connect(app_dsn) as app, app.cursor() as cursor:
            cursor.execute("SELECT session_user,current_user")
            assert cursor.fetchone() == ("pitchlog_app", "pitchlog_app")
        engine = create_database_engine()
        observed: list[str] = []
        event.listen(engine, "commit", lambda connection: observed.append("commit"))
        event.listen(engine, "rollback", lambda connection: observed.append("rollback"))

        def _record_sql(
            connection: object,
            cursor: object,
            statement: str,
            parameters: object,
            context: object,
            executemany: bool,
        ) -> None:
            """関数実呼出し回数だけを記録し、SQL/資格/入力を記録しない。"""
            if "public.resolve_stage_a_rule(" in statement:
                observed.append("resolve")

        event.listen(engine, "before_cursor_execute", _record_sql)
        monkeypatch.setattr(transaction, "create_database_engine", lambda: engine)
        try:
            yield _PublicResolverDatabase(
                admin_dsn, engine, tenant_a, tenant_b, observed
            )
        finally:
            engine.dispose()


def _assert_tenant_guc_cleared(db: _PublicResolverDatabase) -> None:
    """実app接続のcheckout後にtenantが次transactionへ持ち越されない。"""
    with db.engine.connect() as connection:
        assert (
            connection.execute(text("SELECT current_user")).scalar_one()
            == "pitchlog_app"
        )
        assert connection.execute(
            text("SELECT current_setting('app.tenant_id',true)")
        ).scalar_one() in (None, "")


def _assert_rule_lock_released(db: _PublicResolverDatabase) -> None:
    """別の実接続から規則行をNOWAITで更新lockできることを確かめる。"""
    with psycopg.connect(db.admin_dsn) as observer, observer.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM public.rule_sets WHERE id=%s FOR UPDATE NOWAIT",
            (_OFFICIAL_ID,),
        )
        assert cursor.fetchone() == (_OFFICIAL_ID,)


def test_public_resolver_s3_real_scope_success_and_lock_lifetime(
    public_resolver_database: _PublicResolverDatabase,
) -> None:
    """正式関数/実app/実scopeで成功しFOR SHAREを終了まで保持する。"""
    db = public_resolver_database
    context = make_tenant_context(db.tenant_a)
    with transaction.tenant_transaction_scope(context) as scope:
        snapshot = resolve_stage_a_rule(
            scope, StageARuleRequest("game_official", "tournament-a", False)
        )
        with psycopg.connect(db.admin_dsn) as observer:
            with pytest.raises(psycopg.errors.LockNotAvailable):
                with observer.cursor() as cursor:
                    cursor.execute(
                        "SELECT id FROM public.rule_sets WHERE id=%s FOR UPDATE NOWAIT",
                        (_OFFICIAL_ID,),
                    )
    assert db.events == ["resolve", "commit"]
    encoded = encode_applied_rules(snapshot)
    assert snapshot.structural.rule_set_id == _OFFICIAL_ID
    assert encoded["ruleSetId"] == str(_OFFICIAL_ID)
    assert set(encoded) == {
        "ruleSetId",
        "regulationInnings",
        "coldConditions",
        "extensionLimit",
        "tiebreak",
        "dh",
    }
    assert (
        encoded["regulationInnings"] == 9 and type(encoded["regulationInnings"]) is int
    )
    assert encoded["extensionLimit"] == 12 and type(encoded["extensionLimit"]) is int
    tiebreak = cast(dict[str, object], encoded["tiebreak"])
    assert tiebreak["startInning"] == 10 and type(tiebreak["startInning"]) is int
    assert encoded["coldConditions"] == [] and encoded["dh"] is True
    _assert_rule_lock_released(db)
    _assert_tenant_guc_cleared(db)
    with pytest.raises(RuleResolutionError, match="outcome_unconfirmed"):
        resolve_stage_a_rule(
            scope, StageARuleRequest("game_official", "tournament-a", False)
        )
    assert db.events.count("resolve") == 1


def test_public_resolver_s3_parent_visibility_and_tenant_binding(
    public_resolver_database: _PublicResolverDatabase,
) -> None:
    """他tenant親/不存在/無効は同じ失敗となり、別tenantも自己親だけを使う。"""
    db = public_resolver_database
    for key in ("tournament-b", "missing-tournament", "disabled-a"):
        with pytest.raises(RuleResolutionError) as captured:
            with transaction.tenant_transaction_scope(
                make_tenant_context(db.tenant_a)
            ) as scope:
                resolve_stage_a_rule(
                    scope, StageARuleRequest("game_official", key, False)
                )
        assert captured.value.code == "rule_not_available"
    assert db.events == ["resolve", "rollback"] * 3
    with transaction.tenant_transaction_scope(
        make_tenant_context(db.tenant_b)
    ) as scope:
        snapshot = resolve_stage_a_rule(
            scope, StageARuleRequest("game_official", "tournament-b", False)
        )
    assert snapshot.structural.rule_set_id == _OFFICIAL_ID
    _assert_tenant_guc_cleared(db)


def test_public_resolver_s3_override_and_assignment_never_fall_back(
    public_resolver_database: _PublicResolverDatabase,
) -> None:
    """上書き指定/実割当行は全体既定へfallbackせず対象外とする。"""
    db = public_resolver_database
    with pytest.raises(RuleResolutionError, match="stage_a_unsupported"):
        with transaction.tenant_transaction_scope(
            make_tenant_context(db.tenant_a)
        ) as scope:
            resolve_stage_a_rule(
                scope, StageARuleRequest("game_official", "tournament-a", True)
            )
    with psycopg.connect(db.admin_dsn) as admin, admin.cursor() as cursor:
        cursor.execute(
            "INSERT INTO public.tournament_rule_assignments "
            "(tenant_id,tournament_key,rule_set_id) VALUES (%s,'tournament-a',%s)",
            (db.tenant_a, _OFFICIAL_ID),
        )
    with pytest.raises(RuleResolutionError, match="stage_a_unsupported"):
        with transaction.tenant_transaction_scope(
            make_tenant_context(db.tenant_a)
        ) as scope:
            resolve_stage_a_rule(
                scope, StageARuleRequest("game_official", "tournament-a", False)
            )
    assert db.events == ["resolve", "rollback"] * 2
    _assert_rule_lock_released(db)
    _assert_tenant_guc_cleared(db)


def test_public_resolver_s3_invalid_stored_rule_rolls_back(
    public_resolver_database: _PublicResolverDatabase,
) -> None:
    """実規則行の不整合は検証済みsnapshotへ昇格せずrollbackする。"""
    db = public_resolver_database
    with psycopg.connect(db.admin_dsn) as admin, admin.cursor() as cursor:
        cursor.execute(
            "UPDATE public.rule_sets SET extra_innings_limit=10 WHERE id=%s",
            (_OFFICIAL_ID,),
        )
        assert cursor.rowcount == 1
    with pytest.raises(RuleResolutionError, match="invalid_rule"):
        with transaction.tenant_transaction_scope(
            make_tenant_context(db.tenant_a)
        ) as scope:
            resolve_stage_a_rule(
                scope, StageARuleRequest("game_official", "tournament-a", False)
            )
    assert db.events == ["resolve", "rollback"]
    _assert_rule_lock_released(db)
    _assert_tenant_guc_cleared(db)


def test_public_resolver_s3_execute_denial_is_sanitized_and_not_retried(
    public_resolver_database: _PublicResolverDatabase, caplog: pytest.LogCaptureFixture
) -> None:
    """実EXECUTE拒否を秘匿した結果不明へ写し実transactionを全取消する。"""
    db = public_resolver_database
    with psycopg.connect(db.admin_dsn) as admin, admin.cursor() as cursor:
        cursor.execute(
            "REVOKE EXECUTE ON FUNCTION "
            "public.resolve_stage_a_rule(uuid,text,text,boolean) FROM pitchlog_app"
        )
    with pytest.raises(RuleResolutionError) as captured:
        with transaction.tenant_transaction_scope(
            make_tenant_context(db.tenant_a)
        ) as scope:
            resolve_stage_a_rule(
                scope, StageARuleRequest("game_official", "tournament-a", False)
            )
    assert captured.value.code == "outcome_unconfirmed"
    assert str(captured.value) == "outcome_unconfirmed"
    assert "permission denied" not in "".join(
        traceback.format_exception(captured.value)
    )
    assert "permission denied" not in caplog.text
    assert db.events == ["resolve", "rollback"]
    _assert_tenant_guc_cleared(db)
    _assert_rule_lock_released(db)
