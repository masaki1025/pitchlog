"""認証関数の構成、名前解決経路、DB ログの境界を実 DB で検査する。"""

from __future__ import annotations

import time

import psycopg
import pytest
from db_fixtures import _run_docker
from psycopg import sql
from psycopg.conninfo import make_conninfo

from pitchlog.authz.product_authn_contract import (
    AUTHN_FUNCTION_GRANTEES,
    AUTHN_SCHEMA_USERS,
)

from .conftest import ProvisionedProductCatalog
from .test_product_authz_authn_app import (
    _app_dsn,
    _login,
    _seed_identity,
    _seed_settings,
)
from .test_product_authz_authn_limited import _assert_sqlstate, _outsider_dsn

pytestmark = pytest.mark.requires_db


def test_authn_public_and_untrusted_logins_cannot_execute(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """最低要求②: 全 authn 関数で PUBLIC と信頼しない LOGIN の EXECUTE を閉じる。"""
    catalog = provisioned_product_catalog
    _, outsider_dsn = _outsider_dsn(catalog)
    try:
        with catalog.observer.cursor() as cursor:
            cursor.execute(
                """
                SELECT procedure.oid, procedure.proname,
                       pg_catalog.oidvectortypes(procedure.proargtypes)
                FROM pg_catalog.pg_proc AS procedure
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = procedure.pronamespace
                WHERE namespace.nspname = 'authn'
                ORDER BY procedure.proname, procedure.proargtypes
                """
            )
            functions = cursor.fetchall()
            assert {(name, args) for _, name, args in functions} == set(
                AUTHN_FUNCTION_GRANTEES
            )
            cursor.execute(
                """
                SELECT procedure.oid
                FROM pg_catalog.pg_proc AS procedure
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = procedure.pronamespace
                CROSS JOIN LATERAL pg_catalog.aclexplode(
                    COALESCE(procedure.proacl,
                             pg_catalog.acldefault('f', procedure.proowner))
                ) AS privilege
                WHERE namespace.nspname = 'authn'
                  AND privilege.grantee = 0
                  AND privilege.privilege_type = 'EXECUTE'
                """
            )
            assert cursor.fetchall() == []
            cursor.execute(
                """
                SELECT role.rolname, procedure.proname,
                       pg_catalog.oidvectortypes(procedure.proargtypes)
                FROM pg_catalog.pg_roles AS role
                CROSS JOIN pg_catalog.pg_proc AS procedure
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = procedure.pronamespace
                WHERE role.rolcanlogin AND NOT role.rolsuper
                  AND role.rolname NOT IN ('pitchlog_app', 'pitchlog_owner')
                  AND namespace.nspname = 'authn'
                  AND pg_catalog.has_function_privilege(
                      role.oid, procedure.oid, 'EXECUTE')
                """
            )
            assert cursor.fetchall() == []
    finally:
        catalog.observer.rollback()
    with psycopg.connect(outsider_dsn) as connection:
        _assert_sqlstate(
            connection,
            "SELECT authn.login(%s, %s)",
            ("untrusted", None),
        )


def test_authn_schema_acl_and_create_boundary_are_exact(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """認証 2 スキーマの所有・USAGE と、信頼しないロールの CREATE 不可を照合する。"""
    catalog = provisioned_product_catalog
    try:
        with catalog.observer.cursor() as cursor:
            cursor.execute(
                """
                SELECT namespace.nspname, owner.rolname
                FROM pg_catalog.pg_namespace AS namespace
                JOIN pg_catalog.pg_roles AS owner ON owner.oid = namespace.nspowner
                WHERE namespace.nspname IN ('authn', 'authn_crypto')
                """
            )
            assert set(cursor.fetchall()) == {
                (schema, "pitchlog_owner") for schema in AUTHN_SCHEMA_USERS
            }
            cursor.execute(
                """
                SELECT namespace.nspname,
                       COALESCE(grantee.rolname, 'PUBLIC'),
                       privilege.privilege_type, privilege.is_grantable
                FROM pg_catalog.pg_namespace AS namespace
                CROSS JOIN LATERAL pg_catalog.aclexplode(
                    COALESCE(namespace.nspacl,
                             pg_catalog.acldefault('n', namespace.nspowner))
                ) AS privilege
                LEFT JOIN pg_catalog.pg_roles AS grantee
                  ON grantee.oid = privilege.grantee
                WHERE namespace.nspname IN ('authn', 'authn_crypto')
                  AND privilege.grantee <> namespace.nspowner
                """
            )
            assert set(cursor.fetchall()) == {
                (schema, role, "USAGE", False)
                for schema, roles in AUTHN_SCHEMA_USERS.items()
                for role in roles
            }
            cursor.execute(
                """
                SELECT role.rolname, namespace.nspname
                FROM pg_catalog.pg_roles AS role
                CROSS JOIN pg_catalog.pg_namespace AS namespace
                WHERE role.rolcanlogin AND NOT role.rolsuper
                  AND role.rolname <> 'pitchlog_owner'
                  AND namespace.nspname IN ('authn', 'authn_crypto', 'public')
                  AND pg_catalog.has_schema_privilege(
                      role.oid, namespace.oid, 'CREATE')
                """
            )
            assert cursor.fetchall() == []
    finally:
        catalog.observer.rollback()


def test_temp_objects_and_caller_search_path_cannot_hijack_authn(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """最低要求③: 同名の一時関数・演算子・表と呼出側の経路で結果が変わらない。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    identity = _seed_identity(catalog, app_dsn)
    database = catalog.observer.info.dbname
    assert database is not None
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            sql.SQL("GRANT TEMPORARY ON DATABASE {} TO pitchlog_app").format(
                sql.Identifier(database)
            )
        )
    catalog.applicator.commit()

    with psycopg.connect(app_dsn) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SET search_path = pg_temp, authn, authn_crypto, public, pg_catalog"
        )
        cursor.execute("CREATE TEMP TABLE tenants(id uuid)")
        cursor.execute("CREATE TEMP TABLE tenant_tokens(id uuid)")
        cursor.execute(
            """
            CREATE FUNCTION pg_temp.authn_normalize_team_name(text)
            RETURNS text LANGUAGE sql AS $$ SELECT 'hijacked'::text $$
            """
        )
        cursor.execute(
            """
            CREATE FUNCTION pg_temp.text_concat(text, text)
            RETURNS text LANGUAGE sql AS $$ SELECT 'hijacked'::text $$
            """
        )
        cursor.execute(
            """
            CREATE OPERATOR pg_temp.|| (
                LEFTARG = text, RIGHTARG = text,
                FUNCTION = pg_temp.text_concat
            )
            """
        )
        cursor.execute(
            "SELECT pg_temp.authn_normalize_team_name(%s), "
            "'a' OPERATOR(pg_temp.||) 'b'",
            (identity.name,),
        )
        assert cursor.fetchone() == ("hijacked", "hijacked")
        cursor.execute(
            """
            SELECT procedure.proname, procedure.proconfig, procedure.prosecdef
            FROM pg_catalog.pg_proc AS procedure
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = procedure.pronamespace
            WHERE namespace.nspname = 'authn'
            """
        )
        attributes = cursor.fetchall()
        assert {name for name, _, _ in attributes} == {
            name for name, _ in AUTHN_FUNCTION_GRANTEES
        }
        assert all(
            config == ["search_path=pg_catalog, pg_temp"] and security_definer
            for _, config, security_definer in attributes
        )
        cursor.execute("SELECT authn.login(%s, %s)", (identity.name, identity.password))
        row = cursor.fetchone()
        assert row is not None
        token = row[0]
        assert token is not None
        cursor.execute("SELECT authn.verify_token(%s)", (token,))
        assert cursor.fetchone() == (identity.tenant_id,)


def test_authn_is_outside_minimum_requirement_four(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """最低要求④の適用判定: authn は共有対象行を返さないため対象外。"""
    catalog = provisioned_product_catalog
    try:
        with catalog.observer.cursor() as cursor:
            cursor.execute(
                """
                SELECT procedure.proname, procedure.proretset, procedure.prosrc
                FROM pg_catalog.pg_proc AS procedure
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = procedure.pronamespace
                WHERE namespace.nspname = 'authn'
                """
            )
            rows = cursor.fetchall()
            assert {name for name, _, _ in rows} == {
                name for name, _ in AUTHN_FUNCTION_GRANTEES
            }
            assert all(not returns_set for _, returns_set, _ in rows)
            shared_tables = (
                "analysis_groups",
                "group_memberships",
                "sharing_grants",
                "group_invitations",
            )
            assert all(
                table not in body for _, _, body in rows for table in shared_tables
            )
    finally:
        catalog.observer.rollback()


def test_token_id_is_generated_inside_login(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """呼出側に ID 引数がなく、DB の乱数で発行した ID だけが保存される。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    identity = _seed_identity(catalog, app_dsn)
    token = _login(identity)
    assert token is not None
    try:
        with catalog.observer.cursor() as cursor:
            cursor.execute(
                """
                SELECT pg_catalog.pg_get_function_identity_arguments(procedure.oid),
                       procedure.prosrc
                FROM pg_catalog.pg_proc AS procedure
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = procedure.pronamespace
                WHERE namespace.nspname = 'authn' AND procedure.proname = 'login'
                """
            )
            assert (row := cursor.fetchone()) is not None
            assert row[0] == "p_team_name text, p_password text"
            assert "token_id := pg_catalog.gen_random_uuid();" in row[1]
            cursor.execute(
                "SELECT id FROM public.tenant_tokens WHERE tenant_id = %s",
                (identity.tenant_id,),
            )
            assert cursor.fetchall() == [(token,)]
    finally:
        catalog.observer.rollback()


def test_bound_password_is_absent_from_database_logs(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """通常文とエラー文のログでバインド値を隠し、パスワードを出力しない。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    identity = _seed_identity(catalog, app_dsn)
    database = catalog.observer.info.dbname
    assert database is not None
    admin_dsn = make_conninfo(catalog.cluster.admin_dsn, dbname=database)
    with psycopg.connect(admin_dsn, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET log_parameter_max_length = 0")
            cursor.execute("SET log_parameter_max_length_on_error = 0")
            cursor.execute("SET log_statement = 'all'")
            cursor.execute("SET log_min_error_statement = 'error'")
            cursor.execute("SET ROLE pitchlog_app")
            cursor.execute(
                "SELECT current_setting('log_parameter_max_length'), "
                "current_setting('log_parameter_max_length_on_error'), "
                "current_setting('log_statement')"
            )
            assert cursor.fetchone() == ("0", "0", "all")
            try:
                cursor.execute(
                    "SELECT authn.login(%s, %s)",
                    (identity.name, identity.password),
                )
            except psycopg.Error:
                raise AssertionError("認証関数の通常呼出しが失敗した") from None
            try:
                cursor.execute(
                    "SELECT authn.login(%s, %s), 1 / %s",
                    (identity.name, identity.password, 0),
                )
            except psycopg.Error as error:
                if error.sqlstate != "22012":
                    raise AssertionError("予期しない SQLSTATE") from None
            else:
                raise AssertionError("エラー経路を実行できなかった")
            cursor.execute("SELECT 'authn_step10_log_finished'")

    deadline = time.monotonic() + 5
    while True:
        docker_log = _run_docker("logs", catalog.cluster.container_name)
        logged = docker_log.stdout + docker_log.stderr
        if "authn_step10_log_finished" in logged:
            break
        if time.monotonic() >= deadline:
            raise AssertionError("DB ログの終端を確認できなかった")
        time.sleep(0.05)
    if "authn.login" not in logged or "division by zero" not in logged:
        raise AssertionError("通常文またはエラー文の DB ログを確認できなかった")
    if identity.password in logged:
        raise AssertionError("DB ログにバインド値が露出した")
