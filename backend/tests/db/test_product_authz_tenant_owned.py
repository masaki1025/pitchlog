"""製品の tenant-owned RLS を実 PostgreSQL の 2 tenant 行で検証する。"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import psycopg
import pytest
from product_authz_tenant_owned_cases import (
    TENANT_A,
    TENANT_B,
    insert_candidate,
    insert_statement,
    seed_rows,
    tenant_id_table_names,
    tenant_owned_table_names,
    tenant_update_guards,
)
from psycopg import sql
from psycopg.conninfo import make_conninfo

from .conftest import ProvisionedProductCatalog

_POLICY_NAME = "pitchlog_app_tenant_owned"
_APP_ROLE = "pitchlog_app"
_TENANT_PREDICATE = sql.SQL(
    "COALESCE(tenant_id = NULLIF("
    "pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE)"
)
_TENANT_UPDATE_GUARDS = {guard.table: guard for guard in tenant_update_guards()}


def _seed_two_tenants(catalog: ProvisionedProductCatalog) -> None:
    """Superuser で FK 順の A/B 行を投入する。"""
    with catalog.applicator.cursor() as cursor:
        for row in seed_rows():
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


def _set_tenant_context(cursor: psycopg.Cursor[Any], value: str) -> None:
    """現在の transaction だけに tenant 文脈を束縛する。"""
    cursor.execute(
        "SELECT pg_catalog.set_config('app.tenant_id', %s, true)",
        (value,),
    )


def _select_count(
    connection: psycopg.Connection[Any],
    table: str,
    *,
    context: str | None,
    tenant_id: UUID | None,
) -> int:
    """指定文脈で対象表を読み、transaction を必ず閉じる。"""
    try:
        with connection.cursor() as cursor:
            if context is not None:
                _set_tenant_context(cursor, context)
            if tenant_id is None:
                cursor.execute(
                    sql.SQL("SELECT pg_catalog.count(*) FROM {}").format(
                        sql.Identifier("public", table)
                    )
                )
            else:
                cursor.execute(
                    sql.SQL(
                        "SELECT pg_catalog.count(*) FROM {} WHERE tenant_id = %s"
                    ).format(sql.Identifier("public", table)),
                    (tenant_id,),
                )
            row = cursor.fetchone()
        assert row is not None
        return int(row[0])
    finally:
        connection.rollback()


def _assert_sqlstate(expected: str, operation: Callable[[], object]) -> None:
    """操作が指定した PostgreSQL SQLSTATE で拒否されることを表明する。"""
    with pytest.raises(psycopg.Error) as raised:
        operation()
    assert raised.value.sqlstate == expected


def _assert_seed_precondition(
    catalog: ProvisionedProductCatalog,
    table: str,
) -> None:
    """対象表に A/B 双方の行が存在することを RLS 迂回主体で確かめる。"""
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            sql.SQL(
                "SELECT tenant_id, pg_catalog.count(*) FROM {} "
                "WHERE tenant_id IN (%s, %s) GROUP BY tenant_id"
            ).format(sql.Identifier("public", table)),
            (TENANT_A, TENANT_B),
        )
        counts = {row[0]: int(row[1]) for row in cursor.fetchall()}
    catalog.applicator.rollback()
    assert counts.keys() == {TENANT_A, TENANT_B}
    assert all(count > 0 for count in counts.values())


def _insert_other_tenant_row(
    connection: psycopg.Connection[Any],
    table: str,
) -> None:
    """Tenant A の文脈で妥当な tenant B 行を INSERT する。"""
    try:
        with connection.cursor() as cursor:
            _set_tenant_context(cursor, str(TENANT_A))
            statement, params = insert_statement(insert_candidate(table, TENANT_B))
            cursor.execute(statement, params)
    finally:
        connection.rollback()


def _update_rows_to_other_tenant(
    connection: psycopg.Connection[Any],
    table: str,
) -> None:
    """Tenant A の可視行を tenant B 所有へ UPDATE する。"""
    try:
        with connection.cursor() as cursor:
            _set_tenant_context(cursor, str(TENANT_A))
            cursor.execute(
                sql.SQL("UPDATE {} SET tenant_id = %s WHERE tenant_id = %s").format(
                    sql.Identifier("public", table)
                ),
                (TENANT_B, TENANT_A),
            )
    finally:
        connection.rollback()


def _assert_tenant_reassignment_rejected(
    connection: psycopg.Connection[Any],
    table: str,
) -> None:
    """付け替えを RLS または manifest 由来の不変性トリガが拒否する。"""
    with pytest.raises(psycopg.Error) as raised:
        _update_rows_to_other_tenant(connection, table)
    guard = _TENANT_UPDATE_GUARDS.get(table)
    if guard is None:
        assert raised.value.sqlstate == "42501"
        return
    assert raised.value.sqlstate == guard.sqlstate
    assert raised.value.diag.message_primary == guard.message
    assert guard.function_name in (raised.value.diag.context or "")


def _delete_own_rows(
    connection: psycopg.Connection[Any],
    table: str,
) -> None:
    """Tenant A の可視行を DELETE する。"""
    try:
        with connection.cursor() as cursor:
            _set_tenant_context(cursor, str(TENANT_A))
            cursor.execute(
                sql.SQL("DELETE FROM {} WHERE tenant_id = %s").format(
                    sql.Identifier("public", table)
                ),
                (TENANT_A,),
            )
    finally:
        connection.rollback()


@pytest.mark.requires_db
@pytest.mark.parametrize("table", tenant_id_table_names(), ids=tenant_id_table_names())
def test_tenant_id_table_enforces_product_boundary(
    provisioned_product_catalog: ProvisionedProductCatalog,
    table: str,
) -> None:
    """Manifest の tenant_id 全 28 表を表ごとに実 DB で検査する。"""
    catalog = provisioned_product_catalog
    _seed_two_tenants(catalog)
    _assert_seed_precondition(catalog, table)

    with _open_app_connection(catalog) as app:
        try:
            cross_tenant_count = _select_count(
                app,
                table,
                context=str(TENANT_A),
                tenant_id=TENANT_B,
            )
        except psycopg.Error as error:
            assert error.sqlstate == "42501"
            assert table not in tenant_owned_table_names()
            return

        assert cross_tenant_count == 0
        if table not in tenant_owned_table_names():
            return

        assert (
            _select_count(
                app,
                table,
                context=str(TENANT_A),
                tenant_id=TENANT_A,
            )
            > 0
        )
        assert _select_count(app, table, context=None, tenant_id=None) == 0
        assert _select_count(app, table, context="", tenant_id=None) == 0
        _assert_sqlstate(
            "22P02",
            lambda: _select_count(
                app,
                table,
                context="not-a-uuid",
                tenant_id=None,
            ),
        )
        _assert_sqlstate("42501", lambda: _insert_other_tenant_row(app, table))
        _assert_tenant_reassignment_rejected(app, table)
        _assert_sqlstate("42501", lambda: _delete_own_rows(app, table))


def _alter_force(
    catalog: ProvisionedProductCatalog,
    table: str,
    *,
    enabled: bool,
) -> None:
    """変異用に FORCE ROW LEVEL SECURITY を切り替える。"""
    mode = sql.SQL("FORCE") if enabled else sql.SQL("NO FORCE")
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            sql.SQL("ALTER TABLE {} {} ROW LEVEL SECURITY").format(
                sql.Identifier("public", table),
                mode,
            )
        )
    catalog.applicator.commit()


def _create_tenant_owned_policy(
    catalog: ProvisionedProductCatalog,
    table: str,
) -> None:
    """削除変異の後に正規の tenant-owned ポリシーを戻す。"""
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            sql.SQL(
                "CREATE POLICY {} ON {} AS PERMISSIVE FOR ALL TO {} "
                "USING ({}) WITH CHECK ({})"
            ).format(
                sql.Identifier(_POLICY_NAME),
                sql.Identifier("public", table),
                sql.Identifier(_APP_ROLE),
                _TENANT_PREDICATE,
                _TENANT_PREDICATE,
            )
        )
    catalog.applicator.commit()


def _alter_policy_check(
    catalog: ProvisionedProductCatalog,
    table: str,
    expression: sql.Composable,
) -> None:
    """変異用に tenant-owned ポリシーの WITH CHECK を差し替える。"""
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            sql.SQL("ALTER POLICY {} ON {} WITH CHECK ({})").format(
                sql.Identifier(_POLICY_NAME),
                sql.Identifier("public", table),
                expression,
            )
        )
    catalog.applicator.commit()


@pytest.mark.requires_db
def test_policy_force_and_with_check_mutations_change_production_behavior(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """ポリシー削除・NO FORCE・true の各変異を観測し、必ず復元する。"""
    catalog = provisioned_product_catalog
    table = "idempotency_ledger"
    _seed_two_tenants(catalog)
    _assert_seed_precondition(catalog, table)

    with _open_app_connection(catalog) as app:
        assert (
            _select_count(
                app,
                table,
                context=str(TENANT_A),
                tenant_id=TENANT_A,
            )
            > 0
        )
        with catalog.applicator.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP POLICY {} ON {}").format(
                    sql.Identifier(_POLICY_NAME),
                    sql.Identifier("public", table),
                )
            )
        catalog.applicator.commit()
        try:
            assert (
                _select_count(
                    app,
                    table,
                    context=str(TENANT_A),
                    tenant_id=TENANT_A,
                )
                == 0
            )
        finally:
            _create_tenant_owned_policy(catalog, table)
        assert (
            _select_count(
                app,
                table,
                context=str(TENANT_A),
                tenant_id=TENANT_A,
            )
            > 0
        )

        _assert_sqlstate("42501", lambda: _insert_other_tenant_row(app, table))
        _alter_policy_check(catalog, table, sql.SQL("true"))
        try:
            with app.cursor() as cursor:
                _set_tenant_context(cursor, str(TENANT_A))
                statement, params = insert_statement(insert_candidate(table, TENANT_B))
                cursor.execute(statement, params)
                assert cursor.rowcount == 1
            app.rollback()
        finally:
            app.rollback()
            _alter_policy_check(catalog, table, _TENANT_PREDICATE)
        _assert_sqlstate("42501", lambda: _insert_other_tenant_row(app, table))

    with psycopg.connect(catalog.owner_dsn) as owner:
        assert (
            _select_count(
                owner,
                table,
                context=str(TENANT_A),
                tenant_id=TENANT_B,
            )
            == 0
        )
        _alter_force(catalog, table, enabled=False)
        try:
            assert (
                _select_count(
                    owner,
                    table,
                    context=str(TENANT_A),
                    tenant_id=TENANT_B,
                )
                > 0
            )
        finally:
            _alter_force(catalog, table, enabled=True)
        assert (
            _select_count(
                owner,
                table,
                context=str(TENANT_A),
                tenant_id=TENANT_B,
            )
            == 0
        )
