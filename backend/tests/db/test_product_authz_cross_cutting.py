"""製品認可の横断的な境界を実 PostgreSQL で検証する。"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import psycopg
import pytest
from product_authz_cross_cutting_cases import (
    TriggerExpectation,
    trigger_expectations,
    trigger_update_column,
)
from product_authz_other_profiles_cases import (
    control_matrix_cases,
    manifest_table_names,
    other_profile_seed_rows,
)
from product_authz_tenant_owned_cases import TENANT_A, insert_statement
from psycopg import sql
from psycopg.conninfo import make_conninfo

from .conftest import ProvisionedProductCatalog

pytestmark = pytest.mark.requires_db

_APP_ROLE = "pitchlog_app"
_HELPER_SCHEMA = "authz_private"
_HELPER_NAME = "tenant_has_effective_membership"
_TEMP_ROLE = "pitchlog_step9_temp_role"

_TRIGGER_CATALOG_QUERY = """
SELECT routine.proname,
       relation.relname,
       trigger.tgname,
       (trigger.tgtype & 8) <> 0 AS fires_on_delete,
       ARRAY(
           SELECT attribute.attname
           FROM pg_catalog.unnest(trigger.tgattr) WITH ORDINALITY
                AS trigger_attribute(attnum, position)
           JOIN pg_catalog.pg_attribute AS attribute
             ON attribute.attrelid = trigger.tgrelid
            AND attribute.attnum = trigger_attribute.attnum
           ORDER BY trigger_attribute.position
       ) AS update_columns
FROM pg_catalog.pg_trigger AS trigger
JOIN pg_catalog.pg_class AS relation ON relation.oid = trigger.tgrelid
JOIN pg_catalog.pg_namespace AS relation_namespace
  ON relation_namespace.oid = relation.relnamespace
JOIN pg_catalog.pg_proc AS routine ON routine.oid = trigger.tgfoid
JOIN pg_catalog.pg_namespace AS routine_namespace
  ON routine_namespace.oid = routine.pronamespace
WHERE NOT trigger.tgisinternal
  AND relation_namespace.nspname = 'public'
  AND routine_namespace.nspname = 'public'
  AND routine.proname = ANY(%s)
ORDER BY routine.proname
"""


@dataclass(frozen=True, slots=True)
class _AttachedTrigger:
    """実カタログに接続されたトリガと発火操作を保持する。"""

    expectation: TriggerExpectation
    table: str
    trigger_name: str
    fires_on_delete: bool
    update_column: str | None


def _seed_all_tables(catalog: ProvisionedProductCatalog) -> None:
    """外部適用主体で全プロファイルの対象行を FK 順に作る。"""
    with catalog.applicator.cursor() as cursor:
        for row in other_profile_seed_rows():
            statement, params = insert_statement(row)
            cursor.execute(statement, params)
    catalog.applicator.commit()


def _attached_triggers(
    cursor: psycopg.Cursor[Any],
) -> tuple[_AttachedTrigger, ...]:
    """期待する 37 関数と実カタログのトリガ接続を exact-set 照合する。"""
    expectations = trigger_expectations()
    by_name = {item.function_name: item for item in expectations}
    cursor.execute(_TRIGGER_CATALOG_QUERY, (list(by_name),))
    rows = tuple(cursor.fetchall())
    observed_names = tuple(str(row[0]) for row in rows)
    if len(rows) != 37 or set(observed_names) != set(by_name):
        raise AssertionError(
            "37 個の migration トリガ関数が 1 対 1 で接続されていない: "
            f"observed={observed_names}"
        )

    result: list[_AttachedTrigger] = []
    for function_name, table, trigger_name, fires_on_delete, update_columns in rows:
        if not isinstance(update_columns, list) or not all(
            isinstance(column, str) for column in update_columns
        ):
            raise AssertionError(f"トリガ対象列が不正: {function_name}")
        is_delete = bool(fires_on_delete)
        table_name = str(table)
        result.append(
            _AttachedTrigger(
                expectation=by_name[str(function_name)],
                table=table_name,
                trigger_name=str(trigger_name),
                fires_on_delete=is_delete,
                update_column=(
                    None
                    if is_delete
                    else trigger_update_column(table_name, tuple(update_columns))
                ),
            )
        )
    return tuple(result)


def _set_local_app_role(cursor: psycopg.Cursor[Any]) -> None:
    """現在の transaction だけで pitchlog_app として操作する。"""
    cursor.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(_APP_ROLE)))


def _set_tenant_context(cursor: psycopg.Cursor[Any]) -> None:
    """現在の transaction にテナント A の文脈を束縛する。"""
    cursor.execute(
        "SELECT pg_catalog.set_config('app.tenant_id', %s, true)",
        (str(TENANT_A),),
    )


def _assert_trigger_rejection(
    cursor: psycopg.Cursor[Any],
    trigger: _AttachedTrigger,
) -> None:
    """アプリロールの書き込みが指定トリガ固有の例外へ到達すると示す。"""
    cursor.execute("SAVEPOINT product_trigger_case")
    try:
        if trigger.fires_on_delete:
            cursor.execute(
                sql.SQL("DELETE FROM {}").format(
                    sql.Identifier("public", trigger.table)
                )
            )
        else:
            update_column = trigger.update_column
            if update_column is None:
                raise AssertionError(f"UPDATE 対象列が無い: {trigger}")
            cursor.execute(
                sql.SQL("UPDATE {} SET {} = NULL WHERE {} IS NOT NULL").format(
                    sql.Identifier("public", trigger.table),
                    sql.Identifier(update_column),
                    sql.Identifier(update_column),
                )
            )
    except psycopg.Error as error:
        cursor.execute("ROLLBACK TO SAVEPOINT product_trigger_case")
        cursor.execute("RELEASE SAVEPOINT product_trigger_case")
        assert error.sqlstate == trigger.expectation.sqlstate, trigger
        assert error.diag.message_primary == trigger.expectation.message, trigger
    else:
        cursor.execute("ROLLBACK TO SAVEPOINT product_trigger_case")
        cursor.execute("RELEASE SAVEPOINT product_trigger_case")
        pytest.fail(
            "migration トリガがアプリロールの書き込みを拒否しなかった: "
            f"{trigger.expectation.function_name}/{trigger.trigger_name}"
        )


@contextmanager
def _open_app_connection(
    catalog: ProvisionedProductCatalog,
) -> Iterator[psycopg.Connection[Any]]:
    """試験専用 password で pitchlog_app の接続を開く。"""
    password = secrets.token_urlsafe(24)
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                sql.Identifier(_APP_ROLE),
                sql.Literal(password),
            )
        )
    catalog.applicator.commit()
    dsn = make_conninfo(catalog.owner_dsn, user=_APP_ROLE, password=password)
    with psycopg.connect(dsn) as connection:
        yield connection


def _current_database(cursor: psycopg.Cursor[Any]) -> str:
    """現在の DB 名を返す。"""
    cursor.execute("SELECT pg_catalog.current_database()")
    row = cursor.fetchone()
    assert row is not None and isinstance(row[0], str)
    return row[0]


def _create_temp_role(catalog: ProvisionedProductCatalog, password: str) -> str:
    """TEMPORARY と補助関数だけを使える試験ロールを作る。"""
    with catalog.applicator.cursor() as cursor:
        database = _current_database(cursor)
        cursor.execute(
            sql.SQL(
                "CREATE ROLE {} WITH LOGIN NOSUPERUSER NOBYPASSRLS "
                "NOCREATEROLE NOCREATEDB NOREPLICATION NOINHERIT PASSWORD {}"
            ).format(sql.Identifier(_TEMP_ROLE), sql.Literal(password))
        )
        cursor.execute(
            sql.SQL("GRANT CONNECT, TEMPORARY ON DATABASE {} TO {}").format(
                sql.Identifier(database),
                sql.Identifier(_TEMP_ROLE),
            )
        )
        cursor.execute(
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                sql.Identifier(_HELPER_SCHEMA),
                sql.Identifier(_TEMP_ROLE),
            )
        )
        cursor.execute(
            sql.SQL("GRANT EXECUTE ON FUNCTION {}.{}(uuid, boolean) TO {}").format(
                sql.Identifier(_HELPER_SCHEMA),
                sql.Identifier(_HELPER_NAME),
                sql.Identifier(_TEMP_ROLE),
            )
        )
    catalog.applicator.commit()
    return make_conninfo(catalog.owner_dsn, user=_TEMP_ROLE, password=password)


def _drop_temp_role(catalog: ProvisionedProductCatalog) -> None:
    """試験ロールの全付与を剥奪してクラスタから削除する。"""
    catalog.applicator.rollback()
    with catalog.applicator.cursor() as cursor:
        database = _current_database(cursor)
        cursor.execute(
            sql.SQL("REVOKE CONNECT, TEMPORARY ON DATABASE {} FROM {}").format(
                sql.Identifier(database),
                sql.Identifier(_TEMP_ROLE),
            )
        )
        cursor.execute(
            sql.SQL("REVOKE USAGE ON SCHEMA {} FROM {}").format(
                sql.Identifier(_HELPER_SCHEMA),
                sql.Identifier(_TEMP_ROLE),
            )
        )
        cursor.execute(
            sql.SQL("REVOKE EXECUTE ON FUNCTION {}.{}(uuid, boolean) FROM {}").format(
                sql.Identifier(_HELPER_SCHEMA),
                sql.Identifier(_HELPER_NAME),
                sql.Identifier(_TEMP_ROLE),
            )
        )
        cursor.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(_TEMP_ROLE)))
        cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(_TEMP_ROLE)))
    catalog.applicator.commit()


def _helper_result(
    cursor: psycopg.Cursor[Any],
    group_id: object,
) -> bool:
    """スキーマ修飾した補助関数の一般メンバー判定を返す。"""
    cursor.execute(
        "SELECT authz_private.tenant_has_effective_membership(%s, false)",
        (group_id,),
    )
    row = cursor.fetchone()
    assert row is not None and isinstance(row[0], bool)
    return row[0]


def test_all_trigger_functions_fire_without_app_execute_privilege(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """PUBLIC 剥奪後も 37 トリガがアプリロールの書き込みで発火する。"""
    catalog = provisioned_product_catalog
    _seed_all_tables(catalog)
    try:
        with catalog.applicator.cursor() as cursor:
            triggers = _attached_triggers(cursor)
            for table in sorted({trigger.table for trigger in triggers}):
                cursor.execute(
                    sql.SQL("ALTER TABLE {} DISABLE ROW LEVEL SECURITY").format(
                        sql.Identifier("public", table)
                    )
                )
            for trigger in triggers:
                if trigger.fires_on_delete:
                    cursor.execute(
                        sql.SQL("GRANT DELETE ON TABLE {} TO {}").format(
                            sql.Identifier("public", trigger.table),
                            sql.Identifier(_APP_ROLE),
                        )
                    )
                    continue
                update_column = trigger.update_column
                if update_column is None:
                    raise AssertionError(f"UPDATE 対象列が無い: {trigger}")
                cursor.execute(
                    sql.SQL("GRANT SELECT ({}), UPDATE ({}) ON TABLE {} TO {}").format(
                        sql.Identifier(update_column),
                        sql.Identifier(update_column),
                        sql.Identifier("public", trigger.table),
                        sql.Identifier(_APP_ROLE),
                    )
                )
            _set_local_app_role(cursor)
            _set_tenant_context(cursor)
            cursor.execute(
                "SELECT routine.proname, "
                "pg_catalog.has_function_privilege("
                "current_user, routine.oid, 'EXECUTE') "
                "FROM pg_catalog.pg_proc AS routine "
                "JOIN pg_catalog.pg_namespace AS namespace "
                "ON namespace.oid = routine.pronamespace "
                "WHERE namespace.nspname = 'public' "
                "AND routine.proname = ANY(%s) "
                "ORDER BY routine.proname",
                ([trigger.expectation.function_name for trigger in triggers],),
            )
            privileges = tuple(cursor.fetchall())
            assert len(privileges) == 37
            assert all(row[1] is False for row in privileges)
            for trigger in triggers:
                _assert_trigger_rejection(cursor, trigger)
    finally:
        catalog.applicator.rollback()


def test_force_rls_applies_to_owner_with_unbound_context(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """全 RLS 表の所有者にも FORCE が効き、未束縛なら 0 行になる。"""
    catalog = provisioned_product_catalog
    _seed_all_tables(catalog)
    with psycopg.connect(catalog.owner_dsn) as owner:
        with owner.cursor() as cursor:
            cursor.execute("SELECT pg_catalog.current_setting('app.tenant_id', true)")
            assert cursor.fetchone() == (None,)
            for table in manifest_table_names():
                cursor.execute(
                    sql.SQL("SELECT pg_catalog.count(*) FROM {}").format(
                        sql.Identifier("public", table)
                    )
                )
                assert cursor.fetchone() == (0,), table
        owner.rollback()


def test_app_reaches_no_dangerous_role_endpoint(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """SET・INHERIT・ADMIN の推移閉包と危険ロールの交差が空である。"""
    catalog = provisioned_product_catalog
    try:
        with catalog.observer.cursor() as cursor:
            cursor.execute(
                """
                WITH RECURSIVE reachable(role_oid) AS (
                    SELECT oid
                    FROM pg_catalog.pg_roles
                    WHERE rolname = 'pitchlog_app'
                  UNION
                    SELECT membership.roleid
                    FROM reachable
                    JOIN pg_catalog.pg_auth_members AS membership
                      ON membership.member = reachable.role_oid
                    WHERE membership.set_option
                       OR membership.inherit_option
                       OR membership.admin_option
                ),
                dangerous(role_oid) AS (
                    SELECT oid FROM pg_catalog.pg_roles
                    WHERE rolsuper OR rolbypassrls
                  UNION
                    SELECT datdba FROM pg_catalog.pg_database
                    WHERE datname = pg_catalog.current_database()
                  UNION
                    SELECT nspowner FROM pg_catalog.pg_namespace
                    WHERE nspname IN ('public', 'authz_private')
                  UNION
                    SELECT relation.relowner
                    FROM pg_catalog.pg_class AS relation
                    JOIN pg_catalog.pg_namespace AS namespace
                      ON namespace.oid = relation.relnamespace
                    WHERE namespace.nspname = 'public'
                      AND relation.relkind IN ('r', 'p')
                  UNION
                    SELECT routine.proowner
                    FROM pg_catalog.pg_proc AS routine
                    JOIN pg_catalog.pg_namespace AS namespace
                      ON namespace.oid = routine.pronamespace
                    WHERE namespace.nspname IN ('public', 'authz_private')
                )
                SELECT role.rolname
                FROM reachable
                JOIN dangerous ON dangerous.role_oid = reachable.role_oid
                JOIN pg_catalog.pg_roles AS role ON role.oid = reachable.role_oid
                WHERE role.rolname <> 'pitchlog_app'
                ORDER BY role.rolname
                """
            )
            assert cursor.fetchall() == []
    finally:
        catalog.observer.rollback()


def test_untrusted_logins_and_public_lack_effective_helper_execute(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """PUBLIC と全 untrusted LOGIN が補助関数を実効実行できない。"""
    catalog = provisioned_product_catalog
    try:
        with catalog.observer.cursor() as cursor:
            cursor.execute(
                """
                WITH helper AS (
                    SELECT routine.oid, routine.proowner, routine.proacl
                    FROM pg_catalog.pg_proc AS routine
                    JOIN pg_catalog.pg_namespace AS namespace
                      ON namespace.oid = routine.pronamespace
                    WHERE namespace.nspname = 'authz_private'
                      AND routine.proname = 'tenant_has_effective_membership'
                      AND routine.proargtypes = '2950 16'::pg_catalog.oidvector
                ),
                environment_superuser AS (
                    SELECT oid
                    FROM pg_catalog.pg_roles
                    WHERE rolname = current_user AND rolsuper
                )
                SELECT role.rolname,
                       pg_catalog.has_function_privilege(
                           role.oid, helper.oid, 'EXECUTE'
                       ) AS can_execute
                FROM helper
                CROSS JOIN pg_catalog.pg_roles AS role
                WHERE role.rolcanlogin
                  AND role.oid <> helper.proowner
                  AND role.oid NOT IN (SELECT oid FROM environment_superuser)
                ORDER BY role.rolname
                """
            )
            role_privileges = tuple(cursor.fetchall())
            assert _APP_ROLE in {row[0] for row in role_privileges}
            assert all(row[1] is False for row in role_privileges)

            cursor.execute(
                """
                SELECT pg_catalog.count(*)
                FROM pg_catalog.pg_proc AS routine
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = routine.pronamespace
                CROSS JOIN LATERAL pg_catalog.aclexplode(
                    COALESCE(
                        routine.proacl,
                        pg_catalog.acldefault('f', routine.proowner)
                    )
                ) AS privilege
                WHERE namespace.nspname = 'authz_private'
                  AND routine.proname = 'tenant_has_effective_membership'
                  AND routine.proargtypes = '2950 16'::pg_catalog.oidvector
                  AND privilege.grantee = 0
                  AND privilege.privilege_type = 'EXECUTE'
                """
            )
            assert cursor.fetchone() == (0,)
    finally:
        catalog.observer.rollback()


def test_app_cannot_create_temporary_table(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """pitchlog_app は DB の TEMPORARY 権限を持たない。"""
    catalog = provisioned_product_catalog
    with _open_app_connection(catalog) as app:
        try:
            with app.cursor() as cursor, pytest.raises(psycopg.Error) as raised:
                cursor.execute("CREATE TEMPORARY TABLE step9_forbidden(value integer)")
            assert raised.value.sqlstate == "42501"
        finally:
            app.rollback()


def test_temp_schema_shadowing_does_not_change_helper_result(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """TEMPORARY ロールの同名表は固定 search_path の補助関数に効かない。"""
    catalog = provisioned_product_catalog
    _seed_all_tables(catalog)
    admin_case = next(
        case for case in control_matrix_cases() if case.case_id == "admin"
    )
    password = secrets.token_urlsafe(24)
    dsn = _create_temp_role(catalog, password)
    try:
        with psycopg.connect(dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET search_path = pg_catalog, pg_temp")
                cursor.execute(
                    "SELECT routine.proconfig "
                    "FROM pg_catalog.pg_proc AS routine "
                    "JOIN pg_catalog.pg_namespace AS namespace "
                    "ON namespace.oid = routine.pronamespace "
                    "WHERE namespace.nspname = 'authz_private' "
                    "AND routine.proname = 'tenant_has_effective_membership' "
                    "AND routine.proargtypes = '2950 16'::pg_catalog.oidvector"
                )
                assert cursor.fetchone() == (["search_path=pg_catalog, pg_temp"],)
                cursor.execute(
                    "SELECT pg_catalog.set_config('app.tenant_id', %s, true)",
                    (str(admin_case.tenant_id),),
                )
                before = _helper_result(cursor, admin_case.group_id)
                cursor.execute(
                    "CREATE TEMPORARY TABLE tenants(id uuid, enabled boolean)"
                )
                cursor.execute(
                    "CREATE TEMPORARY TABLE analysis_groups(id uuid, status text)"
                )
                cursor.execute(
                    "CREATE TEMPORARY TABLE group_memberships("
                    "group_id uuid, tenant_id uuid, role text, status text)"
                )
                cursor.execute(
                    "CREATE TEMPORARY TABLE tenant_has_effective_membership("
                    "result boolean)"
                )
                after = _helper_result(cursor, admin_case.group_id)
                assert before is True
                assert after is before
            connection.rollback()
    finally:
        _drop_temp_role(catalog)


def test_app_can_execute_no_security_definer_function(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """pitchlog_app が実効実行できる利用者定義 SECURITY DEFINER は 0 件。"""
    catalog = provisioned_product_catalog
    try:
        with catalog.observer.cursor() as cursor:
            cursor.execute(
                """
                SELECT namespace.nspname, routine.proname,
                       pg_catalog.oidvectortypes(routine.proargtypes)
                FROM pg_catalog.pg_proc AS routine
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = routine.pronamespace
                JOIN pg_catalog.pg_roles AS app ON app.rolname = 'pitchlog_app'
                WHERE routine.prosecdef
                  AND namespace.nspname <> 'information_schema'
                  AND namespace.nspname NOT LIKE 'pg\\_%' ESCAPE '\\'
                  AND pg_catalog.has_function_privilege(
                      app.oid, routine.oid, 'EXECUTE'
                  )
                ORDER BY 1, 2, 3
                """
            )
            assert cursor.fetchall() == []
    finally:
        catalog.observer.rollback()
