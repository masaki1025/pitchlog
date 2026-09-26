"""製品認可のその他 4 プロファイルを実 PostgreSQL で検証する。"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, LiteralString
from uuid import UUID

import psycopg
import pytest
from product_authz_other_profiles_cases import (
    NONEXISTENT_GROUP_ID,
    ControlMatrixCase,
    HelperConditionMutation,
    control_matrix_cases,
    control_resource_table_names,
    function_only_table_names,
    global_read_only_table_names,
    helper_condition_mutations,
    mutated_membership_helper_sql,
    other_profile_seed_rows,
    self_tenant_row_table_names,
)
from product_authz_tenant_owned_cases import (
    TENANT_A,
    TENANT_B,
    insert_statement,
)
from psycopg import sql
from psycopg.conninfo import make_conninfo

from pitchlog.authz.product_catalog import inspect_product_authz_catalog

from .conftest import ProvisionedProductCatalog

pytestmark = pytest.mark.requires_db

_APP_ROLE = "pitchlog_app"
_HELPER_SCHEMA = "authz_private"
_HELPER_NAME = "tenant_has_effective_membership"
_HELPER_SIGNATURE = sql.SQL("{}.{}(uuid, boolean)").format(
    sql.Identifier(_HELPER_SCHEMA), sql.Identifier(_HELPER_NAME)
)


def _seed_other_profiles(catalog: ProvisionedProductCatalog) -> None:
    """外部適用主体で、その他プロファイルの対象行を FK 順に作る。"""
    with catalog.applicator.cursor() as cursor:
        for row in other_profile_seed_rows():
            statement, params = insert_statement(row)
            cursor.execute(statement, params)
    catalog.applicator.commit()


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


def _set_tenant_context(cursor: psycopg.Cursor[Any], tenant_id: UUID) -> None:
    """現在の transaction に tenant 文脈を束縛する。"""
    cursor.execute(
        "SELECT pg_catalog.set_config('app.tenant_id', %s, true)",
        (str(tenant_id),),
    )


def _assert_sqlstate(expected: str, operation: Callable[[], object]) -> None:
    """操作が指定した SQLSTATE で拒否されることを表明する。"""
    with pytest.raises(psycopg.Error) as raised:
        operation()
    assert raised.value.sqlstate == expected


def _select_count(
    connection: psycopg.Connection[Any],
    table: str,
    *,
    tenant_id: UUID | None = None,
    key_column: str | None = None,
    key: object | None = None,
) -> int:
    """アプリ接続で行数を読み、transaction を必ず閉じる。"""
    try:
        with connection.cursor() as cursor:
            if tenant_id is not None:
                _set_tenant_context(cursor, tenant_id)
            statement = sql.SQL("SELECT pg_catalog.count(*) FROM {}").format(
                sql.Identifier("public", table)
            )
            params: tuple[object, ...] = ()
            if key_column is not None:
                statement += sql.SQL(" WHERE {} = %s").format(
                    sql.Identifier(key_column)
                )
                params = (key,)
            cursor.execute(statement, params)
            row = cursor.fetchone()
        assert row is not None
        return int(row[0])
    finally:
        connection.rollback()


def _insert_default_row(
    connection: psycopg.Connection[Any],
    table: str,
) -> None:
    """権限検査を観測するため DEFAULT VALUES を試みる。"""
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("INSERT INTO {} DEFAULT VALUES").format(
                    sql.Identifier("public", table)
                )
            )
    finally:
        connection.rollback()


def _update_tenant_name(connection: psycopg.Connection[Any]) -> None:
    """自テナント行の UPDATE を試みる。"""
    try:
        with connection.cursor() as cursor:
            _set_tenant_context(cursor, TENANT_A)
            cursor.execute(
                "UPDATE public.tenants SET name = name WHERE id = %s",
                (TENANT_A,),
            )
    finally:
        connection.rollback()


def _call_helper_without_grant(connection: psycopg.Connection[Any]) -> None:
    """アプリ接続から非公開の補助関数を呼ぶ。"""
    try:
        with connection.cursor() as cursor:
            _set_tenant_context(cursor, TENANT_A)
            cursor.execute(
                "SELECT authz_private.tenant_has_effective_membership(%s, false)",
                (NONEXISTENT_GROUP_ID,),
            )
    finally:
        connection.rollback()


def _superuser_count(catalog: ProvisionedProductCatalog, table: str) -> int:
    """RLS を迂回する外部適用主体で対象表の行数を返す。"""
    try:
        with catalog.applicator.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT pg_catalog.count(*) FROM {}").format(
                    sql.Identifier("public", table)
                )
            )
            row = cursor.fetchone()
        assert row is not None
        return int(row[0])
    finally:
        catalog.applicator.rollback()


def _assert_two_tenant_rows(
    catalog: ProvisionedProductCatalog,
    query: LiteralString,
) -> None:
    """指定経路が A/B 両テナントの実在行へ到達すると表明する。"""
    try:
        with catalog.applicator.cursor() as cursor:
            cursor.execute(query, (TENANT_A, TENANT_B))
            observed = {row[0] for row in cursor.fetchall()}
        assert observed == {TENANT_A, TENANT_B}
    finally:
        catalog.applicator.rollback()


def _assert_function_only_tenant_preconditions(
    catalog: ProvisionedProductCatalog,
) -> None:
    """Tenant と対応を持つ function_only 表に A/B 行があると示す。"""
    queries = (
        "SELECT DISTINCT tenant_id FROM public.tenant_auth_subjects "
        "WHERE tenant_id IN (%s, %s)",
        "SELECT DISTINCT subject.tenant_id "
        "FROM public.tenant_credentials AS credential "
        "JOIN public.tenant_auth_subjects AS subject "
        "ON subject.id = credential.auth_subject_id "
        "WHERE subject.tenant_id IN (%s, %s)",
        "SELECT DISTINCT tenant_id FROM public.tenant_tokens "
        "WHERE tenant_id IN (%s, %s)",
        "SELECT DISTINCT tenant_id FROM public.admin_operation_logs "
        "WHERE tenant_id IN (%s, %s)",
    )
    for query in queries:
        _assert_two_tenant_rows(catalog, query)


def _bootstrap_superuser_oid(catalog: ProvisionedProductCatalog) -> int:
    """Fixture の外部適用主体である superuser の OID を返す。"""
    try:
        with catalog.applicator.cursor() as cursor:
            cursor.execute(
                "SELECT oid FROM pg_catalog.pg_roles WHERE rolname = current_user"
            )
            row = cursor.fetchone()
        assert row is not None
        role_oid = row[0]
        assert isinstance(role_oid, int) and not isinstance(role_oid, bool)
        return role_oid
    finally:
        catalog.applicator.rollback()


def _assert_catalog_green(
    catalog: ProvisionedProductCatalog,
    privileged_role_oid: int,
) -> None:
    """一時変異の rollback 後に製品カタログが exact-set へ戻ったと示す。"""
    try:
        report = inspect_product_authz_catalog(
            catalog.observer,
            privileged_role_oids=frozenset({privileged_role_oid}),
        )
    finally:
        catalog.observer.rollback()
    assert report.ok
    assert report.violations == ()


def _grant_control_access(cursor: psycopg.Cursor[Any]) -> None:
    """現在の transaction だけで制御資源の検査権限を付ける。"""
    table_identifiers = sql.SQL(", ").join(
        sql.Identifier("public", table) for table in control_resource_table_names()
    )
    cursor.execute(
        sql.SQL("GRANT SELECT ON TABLE {} TO {}").format(
            table_identifiers,
            sql.Identifier(_APP_ROLE),
        )
    )
    cursor.execute(
        sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
            sql.Identifier(_HELPER_SCHEMA),
            sql.Identifier(_APP_ROLE),
        )
    )
    cursor.execute(
        sql.SQL("GRANT EXECUTE ON FUNCTION {} TO {}").format(
            _HELPER_SIGNATURE,
            sql.Identifier(_APP_ROLE),
        )
    )


def _set_local_app_role(cursor: psycopg.Cursor[Any]) -> None:
    """外部適用主体の transaction 内で pitchlog_app として検査する。"""
    cursor.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(_APP_ROLE)))


def _helper_result(
    cursor: psycopg.Cursor[Any],
    group_id: UUID,
    *,
    require_admin: bool,
) -> bool:
    """補助関数の boolean 結果を返す。"""
    cursor.execute(
        "SELECT authz_private.tenant_has_effective_membership(%s, %s)",
        (group_id, require_admin),
    )
    row = cursor.fetchone()
    assert row is not None and isinstance(row[0], bool)
    return row[0]


def _control_table_count(
    cursor: psycopg.Cursor[Any],
    table: str,
    group_id: UUID,
) -> int:
    """指定グループに属する制御資源の可視行数を返す。"""
    if table == "analysis_groups":
        cursor.execute(
            "SELECT pg_catalog.count(*) FROM public.analysis_groups WHERE id = %s",
            (group_id,),
        )
    elif table == "group_memberships":
        cursor.execute(
            "SELECT pg_catalog.count(*) FROM public.group_memberships "
            "WHERE group_id = %s",
            (group_id,),
        )
    elif table == "sharing_grants":
        cursor.execute(
            "SELECT pg_catalog.count(*) FROM public.sharing_grants AS grant_row "
            "JOIN public.group_memberships AS membership "
            "ON membership.id = grant_row.membership_id "
            "WHERE membership.group_id = %s",
            (group_id,),
        )
    elif table == "group_invitations":
        cursor.execute(
            "SELECT pg_catalog.count(*) FROM public.group_invitations "
            "WHERE group_id = %s",
            (group_id,),
        )
    else:
        raise AssertionError(f"未知の制御資源表: {table}")
    row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def _assert_control_preconditions(catalog: ProvisionedProductCatalog) -> None:
    """全行列セルに 4 表の対象行が実在すると表明する。"""
    try:
        with catalog.applicator.cursor() as cursor:
            for case in control_matrix_cases():
                assert (
                    _control_table_count(cursor, "analysis_groups", case.group_id) == 1
                )
                assert (
                    _control_table_count(cursor, "group_memberships", case.group_id)
                    == 1
                )
                assert (
                    _control_table_count(cursor, "sharing_grants", case.group_id) == 1
                )
                assert (
                    _control_table_count(cursor, "group_invitations", case.group_id)
                    == 1
                )
            cursor.execute(
                "SELECT tenant_id, pg_catalog.count(*) "
                "FROM public.group_memberships "
                "WHERE tenant_id IN (%s, %s) GROUP BY tenant_id",
                (TENANT_A, TENANT_B),
            )
            counts = {row[0]: int(row[1]) for row in cursor.fetchall()}
        assert counts.keys() == {TENANT_A, TENANT_B}
        assert all(count > 0 for count in counts.values())
    finally:
        catalog.applicator.rollback()


def _assert_matrix_cell(
    cursor: psycopg.Cursor[Any],
    case: ControlMatrixCase,
) -> None:
    """補助関数と 4 ポリシーの 1 行列行を検査する。"""
    _set_tenant_context(cursor, case.tenant_id)
    assert (
        _helper_result(
            cursor,
            case.group_id,
            require_admin=False,
        )
        is case.general_visible
    )
    assert (
        _helper_result(
            cursor,
            case.group_id,
            require_admin=True,
        )
        is case.invitation_visible
    )
    for table in control_resource_table_names():
        expected = (
            case.invitation_visible
            if table == "group_invitations"
            else case.general_visible
        )
        assert _control_table_count(cursor, table, case.group_id) == int(expected), (
            case.case_id,
            table,
        )


def _assert_mutated_matrix(
    cursor: psycopg.Cursor[Any],
    mutation: HelperConditionMutation,
) -> None:
    """単一条件変異後の補助関数と 4 ポリシーの全セルを検査する。"""
    for case in control_matrix_cases():
        general_visible = case.case_id in mutation.general_visible_cases
        invitation_visible = case.case_id in mutation.invitation_visible_cases
        _set_tenant_context(cursor, case.tenant_id)
        assert (
            _helper_result(cursor, case.group_id, require_admin=False)
            is general_visible
        ), (mutation.condition_id, case.case_id, "general")
        assert (
            _helper_result(cursor, case.group_id, require_admin=True)
            is invitation_visible
        ), (mutation.condition_id, case.case_id, "invitation")
        for table in control_resource_table_names():
            expected = (
                invitation_visible if table == "group_invitations" else general_visible
            )
            assert _control_table_count(cursor, table, case.group_id) == int(
                expected
            ), (
                mutation.condition_id,
                case.case_id,
                table,
            )

    _set_tenant_context(cursor, TENANT_A)
    assert (
        _helper_result(cursor, NONEXISTENT_GROUP_ID, require_admin=False)
        is mutation.nonexistent_general_visible
    ), (mutation.condition_id, "nonexistent", "general")
    assert (
        _helper_result(cursor, NONEXISTENT_GROUP_ID, require_admin=True)
        is mutation.nonexistent_invitation_visible
    ), (mutation.condition_id, "nonexistent", "invitation")


def test_self_tenant_row_filters_and_rejects_update(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """Tenants は自テナント 1 行だけを読み、更新できない。"""
    catalog = provisioned_product_catalog
    _seed_other_profiles(catalog)
    assert self_tenant_row_table_names() == ("tenants",)
    assert _superuser_count(catalog, "tenants") >= 2
    _assert_two_tenant_rows(
        catalog,
        "SELECT id FROM public.tenants WHERE id IN (%s, %s)",
    )

    with _open_app_connection(catalog) as app:
        assert (
            _select_count(
                app,
                "tenants",
                tenant_id=TENANT_A,
                key_column="id",
                key=TENANT_A,
            )
            == 1
        )
        assert (
            _select_count(
                app,
                "tenants",
                tenant_id=TENANT_A,
                key_column="id",
                key=TENANT_B,
            )
            == 0
        )
        _assert_sqlstate("42501", lambda: _update_tenant_name(app))


def test_global_read_only_tables_are_readable_but_not_insertable(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """露出事実由来の 4 表は読み取りだけを許す。"""
    catalog = provisioned_product_catalog
    _seed_other_profiles(catalog)
    with _open_app_connection(catalog) as app:
        for table in global_read_only_table_names():
            assert _superuser_count(catalog, table) > 0, table
            assert _select_count(app, table) > 0, table
            _assert_sqlstate(
                "42501", lambda table=table: _insert_default_row(app, table)
            )


def test_function_only_tables_are_permission_denied_and_grant_mutation_changes_it(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """13 表は 0 行ではなく 42501 になり、SELECT 付与変異を観測する。"""
    catalog = provisioned_product_catalog
    _seed_other_profiles(catalog)
    privileged_role_oid = _bootstrap_superuser_oid(catalog)
    tables = function_only_table_names()
    _assert_function_only_tenant_preconditions(catalog)
    with _open_app_connection(catalog) as app:
        for table in tables:
            assert _superuser_count(catalog, table) >= 2, table
            _assert_sqlstate(
                "42501",
                lambda table=table: _select_count(app, table),
            )

        mutated_table = tables[0]
        try:
            with catalog.applicator.cursor() as cursor:
                cursor.execute(
                    sql.SQL("GRANT SELECT ON TABLE {} TO {}").format(
                        sql.Identifier("public", mutated_table),
                        sql.Identifier(_APP_ROLE),
                    )
                )
                _set_local_app_role(cursor)
                cursor.execute(
                    sql.SQL("SELECT pg_catalog.count(*) FROM {}").format(
                        sql.Identifier("public", mutated_table)
                    )
                )
                row = cursor.fetchone()
                assert row == (0,)
                cursor.execute("RESET ROLE")
        finally:
            catalog.applicator.rollback()

        _assert_catalog_green(catalog, privileged_role_oid)
        _assert_sqlstate("42501", lambda: _select_count(app, mutated_table))


def test_control_resources_and_helper_are_denied_without_temporary_grants(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """制御資源 4 表と補助関数を pitchlog_app へ直接公開しない。"""
    catalog = provisioned_product_catalog
    _seed_other_profiles(catalog)
    _assert_control_preconditions(catalog)
    with _open_app_connection(catalog) as app:
        for table in control_resource_table_names():
            _assert_sqlstate(
                "42501",
                lambda table=table: _select_count(app, table, tenant_id=TENANT_A),
            )
        _assert_sqlstate("42501", lambda: _call_helper_without_grant(app))


def test_control_helper_and_policy_truth_matrix_restores_catalog(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """一時権限下で補助関数と 4 ポリシーの正負行列を全セル検査する。"""
    catalog = provisioned_product_catalog
    _seed_other_profiles(catalog)
    _assert_control_preconditions(catalog)
    privileged_role_oid = _bootstrap_superuser_oid(catalog)

    try:
        with catalog.applicator.cursor() as cursor:
            _grant_control_access(cursor)
            _set_local_app_role(cursor)
            for case in control_matrix_cases():
                _assert_matrix_cell(cursor, case)
            _set_tenant_context(cursor, TENANT_A)
            assert not _helper_result(
                cursor,
                NONEXISTENT_GROUP_ID,
                require_admin=False,
            )
            assert not _helper_result(
                cursor,
                NONEXISTENT_GROUP_ID,
                require_admin=True,
            )
            cursor.execute("RESET ROLE")
    finally:
        catalog.applicator.rollback()

    _assert_catalog_green(catalog, privileged_role_oid)


def test_two_tenant_rule_sets_remain_function_only(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """A/B が別の大会規則を持っても 2 表を直接読めない。"""
    catalog = provisioned_product_catalog
    _seed_other_profiles(catalog)
    try:
        with catalog.applicator.cursor() as cursor:
            cursor.execute(
                "SELECT assignment.tenant_id, assignment.rule_set_id "
                "FROM public.tournament_rule_assignments AS assignment "
                "JOIN public.rule_sets AS rules ON rules.id = assignment.rule_set_id "
                "WHERE assignment.tournament_key LIKE 'step8-tournament-%' "
                "ORDER BY assignment.tenant_id"
            )
            rows = tuple(cursor.fetchall())
        assert {row[0] for row in rows} == {TENANT_A, TENANT_B}
        assert len({row[1] for row in rows}) == 2
    finally:
        catalog.applicator.rollback()

    with _open_app_connection(catalog) as app:
        for table in ("rule_sets", "tournament_rule_assignments"):
            _assert_sqlstate(
                "42501",
                lambda table=table: _select_count(app, table, tenant_id=TENANT_A),
            )


def test_each_removed_helper_condition_changes_its_matrix_cell_and_rolls_back(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """補助関数の 6 条件を 1 個ずつ外し、対応する負セルの反転を観測する。"""
    catalog = provisioned_product_catalog
    _seed_other_profiles(catalog)
    _assert_control_preconditions(catalog)
    privileged_role_oid = _bootstrap_superuser_oid(catalog)

    for mutation in helper_condition_mutations():
        try:
            with catalog.applicator.cursor() as cursor:
                _grant_control_access(cursor)
                _set_local_app_role(cursor)
                for case in control_matrix_cases():
                    _assert_matrix_cell(cursor, case)
                _set_tenant_context(cursor, TENANT_A)
                assert not _helper_result(
                    cursor,
                    NONEXISTENT_GROUP_ID,
                    require_admin=False,
                ), mutation.condition_id
                assert not _helper_result(
                    cursor,
                    NONEXISTENT_GROUP_ID,
                    require_admin=True,
                ), mutation.condition_id
                cursor.execute("RESET ROLE")

                cursor.execute(mutated_membership_helper_sql(mutation).encode())
                _set_local_app_role(cursor)
                _assert_mutated_matrix(cursor, mutation)
                cursor.execute("RESET ROLE")
        finally:
            catalog.applicator.rollback()

        _assert_catalog_green(catalog, privileged_role_oid)
