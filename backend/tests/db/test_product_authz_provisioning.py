"""製品認可 DDL の適用器を使い捨て PostgreSQL で検証する。"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
import pytest
from psycopg import pq, sql
from psycopg.conninfo import make_conninfo

from pitchlog.authz.product_provisioning import (
    ProductProvisioningError,
    apply_product_authz_ddl,
)

from .conftest import ProvisionedProductCatalog

pytestmark = pytest.mark.requires_db

_ROLE_ATTRIBUTES = (
    ("superuser", "rolsuper"),
    ("bypass_rls", "rolbypassrls"),
    ("login", "rolcanlogin"),
    ("create_role", "rolcreaterole"),
    ("create_db", "rolcreatedb"),
    ("replication", "rolreplication"),
    ("inherit", "rolinherit"),
)


def _asset_roles(catalog: ProvisionedProductCatalog) -> dict[str, dict[str, object]]:
    """製品資産のロール宣言を ID で引ける形にする。"""
    rows = catalog.asset["roles"]
    assert isinstance(rows, list)
    assert all(isinstance(row, dict) for row in rows)
    result = {str(row["role_id"]): row for row in rows if isinstance(row, dict)}
    assert len(result) == len(rows)
    return result


def _database_name(catalog: ProvisionedProductCatalog) -> str:
    """適用対象 DB の名前を fixture の接続から得る。"""
    database_name = catalog.applicator.info.dbname
    assert database_name is not None
    return database_name


def _role_rows(
    connection: psycopg.Connection[Any],
    role_ids: tuple[str, ...],
) -> dict[str, tuple[bool, ...]]:
    """7 属性を製品ロールごとに取得する。"""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT rolname, rolsuper, rolbypassrls, rolcanlogin, rolcreaterole,
                   rolcreatedb, rolreplication, rolinherit
            FROM pg_catalog.pg_roles
            WHERE rolname = ANY(%s)
            ORDER BY rolname
            """,
            (list(role_ids),),
        )
        rows = cursor.fetchall()
    connection.rollback()
    return {str(row[0]): tuple(bool(value) for value in row[1:]) for row in rows}


def _expected_role_rows(
    catalog: ProvisionedProductCatalog,
) -> dict[str, tuple[bool, ...]]:
    """資産が宣言する全 7 属性を比較用に返す。"""
    return {
        role_id: tuple(bool(row[asset_name]) for asset_name, _ in _ROLE_ATTRIBUTES)
        for role_id, row in _asset_roles(catalog).items()
    }


def _catalog_fingerprint(
    connection: psycopg.Connection[Any],
    role_ids: tuple[str, ...],
) -> tuple[tuple[object, ...], ...]:
    """前提拒否の前後で製品が触るカタログの内容を記録する。"""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 'role', role.rolname,
                   pg_catalog.concat_ws(
                       ',', role.rolsuper, role.rolbypassrls, role.rolcanlogin,
                       role.rolcreaterole, role.rolcreatedb,
                       role.rolreplication, role.rolinherit
                   )
            FROM pg_catalog.pg_roles AS role
            WHERE role.rolname = ANY(%s)
            UNION ALL
            SELECT 'database', database.datname,
                   pg_catalog.concat_ws(',', database.datdba, database.datacl::text)
            FROM pg_catalog.pg_database AS database
            WHERE database.datname = pg_catalog.current_database()
            UNION ALL
            SELECT 'schema', namespace.nspname,
                   pg_catalog.concat_ws(',', namespace.nspowner, namespace.nspacl::text)
            FROM pg_catalog.pg_namespace AS namespace
            WHERE namespace.nspname IN ('public', 'authz_private')
            UNION ALL
            SELECT 'relation', relation.oid::text,
                   pg_catalog.concat_ws(
                       ',', relation.relowner, relation.relrowsecurity,
                       relation.relforcerowsecurity, relation.relacl::text
                   )
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'public'
            UNION ALL
            SELECT 'policy', policy.oid::text,
                   pg_catalog.concat_ws(
                       ',', policy.polname, policy.polcmd, policy.polpermissive,
                       policy.polroles::text, policy.polqual::text,
                       policy.polwithcheck::text
                   )
            FROM pg_catalog.pg_policy AS policy
            JOIN pg_catalog.pg_class AS relation ON relation.oid = policy.polrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'public'
            UNION ALL
            SELECT 'function', procedure.oid::text,
                   pg_catalog.concat_ws(
                       ',', procedure.proowner, procedure.prosecdef,
                       procedure.proacl::text, procedure.proconfig::text
                   )
            FROM pg_catalog.pg_proc AS procedure
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = procedure.pronamespace
            WHERE namespace.nspname IN ('public', 'authz_private')
            UNION ALL
            SELECT 'column', attribute.attrelid::text || ':' || attribute.attnum,
                   attribute.attacl::text
            FROM pg_catalog.pg_attribute AS attribute
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = attribute.attrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'public'
              AND attribute.attnum > 0
              AND NOT attribute.attisdropped
            ORDER BY 1, 2, 3
            """,
            (list(role_ids),),
        )
        rows = tuple(tuple(row) for row in cursor.fetchall())
    connection.rollback()
    return rows


@contextmanager
def _open_app_connection(
    catalog: ProvisionedProductCatalog,
) -> Iterator[psycopg.Connection[Any]]:
    """試験専用 password を付けた pitchlog_app 接続を開く。"""
    password = secrets.token_urlsafe(24)
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            sql.SQL("ALTER ROLE pitchlog_app PASSWORD {}").format(sql.Literal(password))
        )
    catalog.applicator.commit()
    dsn = make_conninfo(
        catalog.owner_dsn,
        user="pitchlog_app",
        password=password,
    )
    with psycopg.connect(dsn) as connection:
        yield connection


def _assert_rejected_without_catalog_change(
    catalog: ProvisionedProductCatalog,
    connection: psycopg.Connection[Any],
    message: str,
) -> None:
    """公開経路の拒否と、別接続から見たカタログ不変を表明する。"""
    role_ids = tuple(_asset_roles(catalog))
    before = _catalog_fingerprint(catalog.observer, role_ids)
    with pytest.raises(ProductProvisioningError, match=message):
        apply_product_authz_ddl(connection)
    after = _catalog_fingerprint(catalog.observer, role_ids)
    assert after == before


def test_product_fixture_migrates_as_owner_then_applies_as_external_superuser(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """Migration の所有者と適用後の主体・固定 7 手順を実 DB で表明する。"""
    catalog = provisioned_product_catalog
    with catalog.applicator.cursor() as cursor:
        cursor.execute("SELECT current_user::text, session_user::text")
        identity = cursor.fetchone()
        cursor.execute(
            """
            SELECT DISTINCT owner.rolname
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            JOIN pg_catalog.pg_roles AS owner ON owner.oid = relation.relowner
            WHERE namespace.nspname = 'public'
              AND relation.relkind IN ('r', 'p')
            """
        )
        relation_owners = {str(row[0]) for row in cursor.fetchall()}
        cursor.execute(
            """
            SELECT owner.rolname
            FROM pg_catalog.pg_database AS database
            JOIN pg_catalog.pg_roles AS owner ON owner.oid = database.datdba
            WHERE database.datname = pg_catalog.current_database()
            """
        )
        database_owner = cursor.fetchone()
    catalog.applicator.rollback()

    assert identity is not None and identity[0] == identity[1]
    assert catalog.applicator.info.transaction_status is pq.TransactionStatus.IDLE
    assert relation_owners == {"pitchlog_owner"}
    assert database_owner == ("pitchlog_owner",)
    assert tuple(
        step.sequence for step in catalog.application_steps.application_steps
    ) == tuple(range(1, 8))
    assert catalog.application_steps.transaction == "single"

    expected = _expected_role_rows(catalog)
    role_ids = tuple(expected)
    pre_roles = {
        str(row[0]): tuple(bool(value) for value in row[1:])
        for row in catalog.pre_application_catalog.roles
    }
    assert pre_roles == {"pitchlog_owner": expected["pitchlog_owner"]}
    assert _role_rows(catalog.observer, role_ids) == expected


def test_reapplication_normalizes_all_seven_role_attributes(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """全製品ロールの 7 属性を反転しても再適用が資産の値へ戻す。"""
    catalog = provisioned_product_catalog
    roles = _asset_roles(catalog)
    positive_tokens = {
        "superuser": sql.SQL("SUPERUSER"),
        "bypass_rls": sql.SQL("BYPASSRLS"),
        "login": sql.SQL("LOGIN"),
        "create_role": sql.SQL("CREATEROLE"),
        "create_db": sql.SQL("CREATEDB"),
        "replication": sql.SQL("REPLICATION"),
        "inherit": sql.SQL("INHERIT"),
    }
    negative_tokens = {
        "superuser": sql.SQL("NOSUPERUSER"),
        "bypass_rls": sql.SQL("NOBYPASSRLS"),
        "login": sql.SQL("NOLOGIN"),
        "create_role": sql.SQL("NOCREATEROLE"),
        "create_db": sql.SQL("NOCREATEDB"),
        "replication": sql.SQL("NOREPLICATION"),
        "inherit": sql.SQL("NOINHERIT"),
    }
    with catalog.applicator.cursor() as cursor:
        for role_id, declaration in roles.items():
            reversed_attributes = [
                negative_tokens[name]
                if bool(declaration[name])
                else positive_tokens[name]
                for name, _ in _ROLE_ATTRIBUTES
            ]
            cursor.execute(
                sql.SQL("ALTER ROLE {} WITH ").format(sql.Identifier(role_id))
                + sql.SQL(" ").join(reversed_attributes)
            )
    catalog.applicator.commit()

    apply_product_authz_ddl(catalog.applicator)

    expected = _expected_role_rows(catalog)
    assert _role_rows(catalog.observer, tuple(expected)) == expected


def test_all_connection_preconditions_leave_observed_catalog_unchanged(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """5 種の接続前提違反を拒否し、別接続から見たカタログを保つ。"""
    catalog = provisioned_product_catalog
    applicator_dsn = make_conninfo(
        catalog.cluster.admin_dsn,
        dbname=_database_name(catalog),
    )

    closed_connection = psycopg.connect(applicator_dsn)
    closed_connection.close()
    _assert_rejected_without_catalog_change(catalog, closed_connection, "閉じた接続")

    with psycopg.connect(applicator_dsn, autocommit=True) as autocommit_connection:
        _assert_rejected_without_catalog_change(
            catalog,
            autocommit_connection,
            "autocommit",
        )

    with psycopg.connect(applicator_dsn) as busy_connection:
        with busy_connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        assert busy_connection.info.transaction_status is pq.TransactionStatus.INTRANS
        _assert_rejected_without_catalog_change(
            catalog,
            busy_connection,
            "進行中のトランザクション",
        )
        assert busy_connection.info.transaction_status is pq.TransactionStatus.INTRANS
        busy_connection.rollback()

    with psycopg.connect(catalog.owner_dsn) as owner_connection:
        _assert_rejected_without_catalog_change(
            catalog,
            owner_connection,
            "superuser",
        )

    with _open_app_connection(catalog) as app_connection:
        _assert_rejected_without_catalog_change(
            catalog,
            app_connection,
            "pitchlog_app",
        )
