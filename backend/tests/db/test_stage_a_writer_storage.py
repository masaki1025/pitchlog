"""writer配置の原子性・有限再開・改竄拒否を実PGで検証する。"""

from typing import Any, LiteralString, cast

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event

import pitchlog.db.stage_a_startup as startup
from pitchlog.authz.product_provisioning import (
    apply_product_authz_before_rule_placement,
)

from .test_stage_a_rule_candidates import _fresh_schema_database, _owner_url

pytestmark = pytest.mark.requires_db


def _revision(dsn: str) -> str:
    """実markerだけを読み取る。"""
    with psycopg.connect(dsn) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        assert row is not None
        return row[0]


@pytest.mark.parametrize(
    "fault_point",
    [
        "0037_before_admissions",
        "0037_after_admissions",
        "0038_before_stamp",
        "0038_after_stamp",
        "0038_after_revoke",
    ],
)
def test_placement_fault_rolls_back(
    disposable_postgres_cluster: Any, monkeypatch: pytest.MonkeyPatch, fault_point: str
) -> None:
    """writer配置途中の故障はschemaとrevisionを一緒に戻す。"""
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner,
        admin,
    ):
        target = {
            "0037_before_admissions": (
                "before_cursor_execute",
                "CREATE TABLE sync_fence.writer_admissions",
            ),
            "0037_after_admissions": (
                "after_cursor_execute",
                "CREATE TABLE sync_fence.writer_admissions",
            ),
            "0038_before_stamp": (
                "before_cursor_execute",
                "CREATE TABLE sync_fence.first_ball_write_admissions",
            ),
            "0038_after_stamp": (
                "after_cursor_execute",
                "CREATE TABLE sync_fence.first_ball_write_admissions",
            ),
            "0038_after_revoke": (
                "after_cursor_execute",
                "REVOKE ALL ON TABLE sync_fence.first_ball_write_admissions",
            ),
        }[fault_point]
        reached = []

        def fail(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
            if target[1] in statement:
                reached.append(fault_point)
                raise RuntimeError("writer fault")

        event.listen(Engine, target[0], fail)
        try:
            with pytest.raises(RuntimeError, match="writer fault"):
                startup.advance_stage_a_from_s0(owner_dsn=owner, applicator_dsn=admin)
        finally:
            event.remove(Engine, target[0], fail)
        assert reached == [fault_point]
        assert _revision(admin) == "0036_initial_right_storage"
        with psycopg.connect(admin) as connection:
            assert connection.execute(
                "SELECT to_regnamespace('sync_fence')"
            ).fetchone() == (None,)
            assert connection.execute(
                "SELECT count(*) FROM game_type_rule_defaults"
            ).fetchone() == (5,)
        assert not startup.resume_stage_a_after_placement(
            owner_dsn=owner, applicator_dsn=admin
        ).publishable


@pytest.mark.parametrize(
    "revision",
    [
        "0034_stage_a_rule_defaults",
        "0035_rg1_initial_fresh_epoch",
        "0036_initial_right_storage",
        "0037_sync_writer_binding",
        "0038_first_ball_write_admission",
    ],
)
def test_finite_resume(
    disposable_postgres_cluster: Any, monkeypatch: pytest.MonkeyPatch, revision: str
) -> None:
    """既知5段階からだけ再開し、全認可適用後も非公開とする。"""
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner,
        admin,
    ):
        with psycopg.connect(admin) as connection:
            apply_product_authz_before_rule_placement(connection)
        engine = create_engine(_owner_url(owner))
        try:
            with engine.begin() as connection:
                config = Config(str(startup._BACKEND_ROOT / "alembic.ini"))
                config.attributes["connection"] = connection
                command.upgrade(config, revision)
        finally:
            engine.dispose()
        assert _revision(admin) == revision
        for _ in range(2):
            result = startup.resume_stage_a_after_placement(
                owner_dsn=owner, applicator_dsn=admin
            )
            assert result.completed_stage == "S3" and not result.publishable
        startup._require_s3(admin)


@pytest.mark.parametrize(
    "mutation",
    [
        "ALTER SCHEMA sync_fence OWNER TO CURRENT_USER",
        "ALTER TABLE sync_fence.writer_bindings DISABLE ROW LEVEL SECURITY",
        "ALTER TABLE sync_fence.writer_admissions NO FORCE ROW LEVEL SECURITY",
        "ALTER TABLE sync_fence.writer_bindings ALTER COLUMN expires_at DROP NOT NULL",
        "ALTER TABLE sync_fence.writer_bindings DROP CONSTRAINT ck_sy"
        "nc_writer_binding_positive; ALTER TABLE sync_fence.writer_bi"
        "ndings ADD CONSTRAINT ck_sync_writer_binding_positive CHECK "
        "(true)",
        "UPDATE alembic_version SET version_num='0099_unknown'",
        "GRANT CONNECT ON DATABASE pitchlog_disposable TO PUBLIC",
    ],
)
def test_structural_drift_rejected(
    disposable_postgres_cluster: Any, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    """owner/列/制約/RLS/未知revisionを自動修復しない。"""
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner,
        admin,
    ):
        startup.advance_stage_a_from_s0(owner_dsn=owner, applicator_dsn=admin)
        with psycopg.connect(admin) as connection:
            connection.execute(cast(LiteralString, mutation))
        with pytest.raises(startup.StageAStartupError):
            startup.resume_stage_a_after_placement(
                owner_dsn=owner, applicator_dsn=admin
            )


def _full_catalog_snapshot(dsn: str) -> dict[str, tuple[tuple[Any, ...], ...]]:
    """自owned DBの全製品schemaを含む認可/構造面を厳密に記録する。"""
    scope = "n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'"
    queries = {
        "roles": (
            "SELECT "
            "rolname,rolsuper,rolinherit,rolcreaterole,rolcreatedb,rolcanlo"
            "gin,rolreplication,rolconnlimit,rolvaliduntil::text,rolbypassr"
            "ls FROM pg_roles ORDER BY rolname"
        ),
        "memberships": (
            "SELECT "
            "r.rolname,u.rolname,g.rolname,m.admin_option,m.inherit_option,"
            "m.set_option FROM pg_auth_members m JOIN pg_roles r ON "
            "r.oid=m.roleid JOIN pg_roles u ON u.oid=m.member JOIN "
            "pg_roles g ON g.oid=m.grantor ORDER BY 1,2,3"
        ),
        "database_acl": (
            "SELECT datname,pg_get_userbyid(datdba),datacl::text FROM "
            "pg_database ORDER BY datname"
        ),
        "schemas": (
            "SELECT "
            "n.nspname,pg_get_userbyid(n.nspowner),n.nspacl::text FROM "
            "pg_namespace n WHERE {scope} ORDER BY 1"
        ).format(scope=scope),
        "relations": (
            "SELECT "
            "n.nspname,c.relname,c.relkind,pg_get_userbyid(c.relowner),"
            "c.relrowsecurity,c.relforcerowsecurity,c.relacl::text "
            "FROM pg_class c JOIN pg_namespace n ON "
            "n.oid=c.relnamespace WHERE {scope} ORDER BY 1,2"
        ).format(scope=scope),
        "columns": (
            "SELECT "
            "n.nspname,c.relname,a.attname,a.attnum,format_type(a.attty"
            "pid,a.atttypmod),a.attnotnull,a.attidentity,a.attgenerated"
            ",a.attacl::text,pg_get_expr(d.adbin,d.adrelid) FROM "
            "pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN "
            "pg_namespace n ON n.oid=c.relnamespace LEFT JOIN "
            "pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
            "WHERE {scope} AND NOT a.attisdropped ORDER "
            "BY 1,2,4"
        ).format(scope=scope),
        "policies": (
            "SELECT "
            "n.nspname,c.relname,p.polname,p.polcmd,p.polpermissive,ARR"
            "AY(SELECT rolname FROM pg_roles WHERE oid=ANY(p.polroles) "
            "ORDER BY "
            "rolname),p.polroles,pg_get_expr(p.polqual,p.polrelid),pg_g"
            "et_expr(p.polwithcheck,p.polrelid) FROM pg_policy p JOIN "
            "pg_class c ON c.oid=p.polrelid JOIN pg_namespace n ON "
            "n.oid=c.relnamespace WHERE {scope} ORDER BY 1,2,3"
        ).format(scope=scope),
        "functions": (
            "SELECT "
            "n.nspname,p.proname,pg_get_function_identity_arguments(p.o"
            "id),pg_get_userbyid(p.proowner),p.prosecdef,p.proconfig::t"
            "ext,p.proacl::text,pg_get_functiondef(p.oid) FROM pg_proc "
            "p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE "
            "{scope} AND p.prokind IN ('f','p') ORDER BY 1,2,3"
        ).format(scope=scope),
        "constraints": (
            "SELECT "
            "n.nspname,c.relname,k.conname,pg_get_constraintdef(k.oid),"
            "k.convalidated,k.condeferrable,k.condeferred FROM "
            "pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN "
            "pg_namespace n ON n.oid=c.relnamespace WHERE {scope} "
            "ORDER BY 1,2,3"
        ).format(scope=scope),
        "triggers": (
            "SELECT "
            "n.nspname,c.relname,t.tgname,t.tgenabled,pg_get_triggerdef"
            "(t.oid) FROM pg_trigger t JOIN pg_class c ON "
            "c.oid=t.tgrelid JOIN pg_namespace n ON "
            "n.oid=c.relnamespace WHERE {scope} ORDER BY 1,2,3"
        ).format(scope=scope),
        "extensions": (
            "SELECT "
            "e.extname,e.extversion,n.nspname,pg_get_userbyid(e.extowner) "
            "FROM pg_extension e JOIN pg_namespace n ON "
            "n.oid=e.extnamespace ORDER BY 1"
        ),
    }
    # builtin EXECUTEとdefault privilegesも省略せず全schemaで観測する。
    queries["function_acl_all_schemas"] = (
        "SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),"
        "pg_get_userbyid(p.proowner),p.proacl::text FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid=p.pronamespace ORDER BY 1,2,3"
    )
    queries["default_acl"] = (
        "SELECT pg_get_userbyid(d.defaclrole),n.nspname,d.defaclobjtype,"
        "d.defaclacl::text FROM pg_default_acl d LEFT JOIN pg_namespace n "
        "ON n.oid=d.defaclnamespace ORDER BY 1,2,3"
    )
    with psycopg.connect(dsn) as connection:
        return {
            key: tuple(connection.execute(cast(LiteralString, query)).fetchall())
            for key, query in queries.items()
        }


@pytest.mark.parametrize("fault_position", ["early20", "final_statement"])
def test_installer_fault_rollback_and_resume(
    disposable_postgres_cluster: Any,
    monkeypatch: pytest.MonkeyPatch,
    fault_position: str,
) -> None:
    """認可transactionの故障は部分適用を残さず0038から再開する。"""
    original = startup.apply_product_authz_ddl
    snapshots = []

    def fail(connection: Any) -> None:
        snapshots.append(_full_catalog_snapshot(admin))
        import pitchlog.authz.product_provisioning as provisioning

        checkpoint = provisioning._checkpoint_id
        target = (
            20
            if fault_position == "early20"
            else len(
                provisioning._build_operation_statements(
                    provisioning.ProductOperation.APPLY
                )[1]
            )
        )
        count = 0

        def fail_checkpoint(*args: Any) -> Any:
            nonlocal count
            count += 1
            if count == target:
                raise RuntimeError("installer fault")
            return checkpoint(*args)

        with monkeypatch.context() as patch:
            patch.setattr(provisioning, "_checkpoint_id", fail_checkpoint)
            original(connection)

    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as (
        owner,
        admin,
    ):
        monkeypatch.setattr(startup, "apply_product_authz_ddl", fail)
        with pytest.raises(RuntimeError, match="installer fault"):
            startup.advance_stage_a_from_s0(owner_dsn=owner, applicator_dsn=admin)
        assert _revision(admin) == "0038_first_ball_write_admission"
        assert len(snapshots) == 1
        assert _full_catalog_snapshot(admin) == snapshots[0]
        with psycopg.connect(admin) as connection:
            assert connection.execute(
                "SELECT to_regprocedure('public.resolve_stage_a_rule(uuid,tex"
                "t,text,boolean)')"
            ).fetchone() == (None,)
        startup._require_writer_state(admin)
        monkeypatch.setattr(startup, "apply_product_authz_ddl", original)
        assert not startup.resume_stage_a_after_placement(
            owner_dsn=owner, applicator_dsn=admin
        ).publishable
        startup._require_s3(admin)
