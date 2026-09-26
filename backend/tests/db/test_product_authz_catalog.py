"""製品認可カタログの exact-set 検査を実 PostgreSQL で検証する。"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql

from pitchlog.authz.product_catalog import (
    ProductCatalogReport,
    inspect_product_authz_catalog,
)
from pitchlog.authz.product_provisioning import (
    apply_product_authz_ddl,
    unapply_product_authz_ddl,
)

from .conftest import ProvisionedProductCatalog

pytestmark = pytest.mark.requires_db

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _bootstrap_superuser_oid(catalog: ProvisionedProductCatalog) -> int:
    """Fixture の外部適用主体である bootstrap superuser の OID を返す。"""
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            """
            SELECT role.oid
            FROM pg_catalog.pg_roles AS role
            WHERE role.rolname = current_user
            """
        )
        row = cursor.fetchone()
    catalog.applicator.rollback()
    assert row is not None
    role_oid = row[0]
    assert isinstance(role_oid, int) and not isinstance(role_oid, bool)
    return role_oid


def _inspect(catalog: ProvisionedProductCatalog) -> ProductCatalogReport:
    """公開経路で検査し、observer の読み取り transaction を閉じる。"""
    try:
        return inspect_product_authz_catalog(
            catalog.observer,
            privileged_role_oids=frozenset({_bootstrap_superuser_oid(catalog)}),
        )
    finally:
        catalog.observer.rollback()


def _assert_red(
    catalog: ProvisionedProductCatalog,
    expected_check_id: str,
) -> None:
    """公開カタログ検査が指定面の変異を検出することを表明する。"""
    report = _inspect(catalog)
    assert not report.ok
    assert expected_check_id in {violation.check_id for violation in report.violations}


@contextmanager
def _temporary_role(
    catalog: ProvisionedProductCatalog,
    attributes: sql.Composable,
) -> Iterator[str]:
    """一意な試験用ロールを作り、検査後に必ず削除する。"""
    role_name = f"product_catalog_{secrets.token_hex(6)}"
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            sql.SQL("CREATE ROLE {} WITH ").format(sql.Identifier(role_name))
            + attributes
        )
    catalog.applicator.commit()
    try:
        yield role_name
    finally:
        catalog.observer.rollback()
        catalog.applicator.rollback()
        with catalog.applicator.cursor() as cursor:
            cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role_name)))
        catalog.applicator.commit()


def _grant_membership(
    catalog: ProvisionedProductCatalog,
    granted_role: str,
    member_role: str,
    *,
    admin: bool,
) -> None:
    """全 option を明示して試験用 membership 辺を作る。"""
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            sql.SQL("GRANT {} TO {} WITH ADMIN {}, INHERIT FALSE, SET FALSE").format(
                sql.Identifier(granted_role),
                sql.Identifier(member_role),
                sql.SQL("TRUE" if admin else "FALSE"),
            )
        )
    catalog.applicator.commit()


def _revoke_membership(
    catalog: ProvisionedProductCatalog,
    granted_role: str,
    member_role: str,
) -> None:
    """試験用 membership 辺を削除する。"""
    catalog.observer.rollback()
    catalog.applicator.rollback()
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            sql.SQL("REVOKE {} FROM {}").format(
                sql.Identifier(granted_role),
                sql.Identifier(member_role),
            )
        )
    catalog.applicator.commit()


def _migration_trigger_function(
    catalog: ProvisionedProductCatalog,
) -> tuple[str, str]:
    """資産から引数なし migration trigger 関数を 1 つ選ぶ。"""
    raw_functions = catalog.asset["functions"]
    assert isinstance(raw_functions, list)
    for row in raw_functions:
        if not isinstance(row, dict) or row.get("function_kind") != "migration_trigger":
            continue
        assert row.get("identity_args") == ""
        return str(row["schema_name"]), str(row["function_name"])
    raise AssertionError("migration trigger 関数が資産にない")


def _alter_function_security(
    catalog: ProvisionedProductCatalog,
    schema_name: str,
    function_name: str,
    mode: str,
) -> None:
    """指定した引数なし関数の security mode を試験用に変更する。"""
    assert mode in {"DEFINER", "INVOKER"}
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            sql.SQL("ALTER FUNCTION {}.{}() SECURITY ").format(
                sql.Identifier(schema_name),
                sql.Identifier(function_name),
            )
            + sql.SQL(mode)
        )
    catalog.applicator.commit()


def test_applied_product_catalog_is_green(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """全カタログ面が一致し、呼び出し側の search_path を保存する。"""
    catalog = provisioned_product_catalog
    privileged_role_oid = _bootstrap_superuser_oid(catalog)
    try:
        with catalog.observer.cursor() as cursor:
            cursor.execute("SET LOCAL search_path = public, pg_catalog")
            cursor.execute("SELECT pg_catalog.current_setting('search_path')")
            before = cursor.fetchone()
        report = inspect_product_authz_catalog(
            catalog.observer,
            privileged_role_oids=frozenset({privileged_role_oid}),
        )
        with catalog.observer.cursor() as cursor:
            cursor.execute("SELECT pg_catalog.current_setting('search_path')")
            after = cursor.fetchone()
    finally:
        catalog.observer.rollback()

    assert report.ok
    assert report.violations == ()
    assert before == ("public, pg_catalog",)
    assert after == before


def test_admin_only_membership_edge_is_red(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """製品ロールを ADMIN だけで付与した辺も拒否する。"""
    catalog = provisioned_product_catalog
    granted_role = "pitchlog_shared_fn_owner"
    with _temporary_role(catalog, sql.SQL("NOLOGIN")) as member_role:
        _grant_membership(
            catalog,
            granted_role,
            member_role,
            admin=True,
        )
        try:
            _assert_red(catalog, "PRODUCT-CATALOG:MEMBERSHIPS")
        finally:
            _revoke_membership(catalog, granted_role, member_role)


def test_membership_edge_from_product_role_is_red(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """製品ロールを member とする外向きの辺を拒否する。"""
    catalog = provisioned_product_catalog
    member_role = "pitchlog_app"
    with _temporary_role(catalog, sql.SQL("NOLOGIN")) as granted_role:
        _grant_membership(
            catalog,
            granted_role,
            member_role,
            admin=False,
        )
        try:
            _assert_red(catalog, "PRODUCT-CATALOG:MEMBERSHIPS")
        finally:
            _revoke_membership(catalog, granted_role, member_role)


def test_unlisted_login_bypassrls_role_is_red(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """許可集合にない LOGIN + BYPASSRLS ロールを拒否する。"""
    with _temporary_role(
        provisioned_product_catalog,
        sql.SQL("LOGIN NOSUPERUSER BYPASSRLS"),
    ):
        _assert_red(
            provisioned_product_catalog,
            "PRODUCT-CATALOG:DANGEROUS-LOGIN-ROLES",
        )


def test_unlisted_login_superuser_is_red(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """入力 OID にない LOGIN superuser を拒否する。"""
    with _temporary_role(
        provisioned_product_catalog,
        sql.SQL("LOGIN SUPERUSER NOBYPASSRLS"),
    ):
        _assert_red(
            provisioned_product_catalog,
            "PRODUCT-CATALOG:DANGEROUS-LOGIN-ROLES",
        )


def test_security_definer_trigger_function_is_red(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """Migration trigger 関数 1 個の SECURITY DEFINER 化を拒否する。"""
    catalog = provisioned_product_catalog
    schema_name, function_name = _migration_trigger_function(catalog)
    _alter_function_security(catalog, schema_name, function_name, "DEFINER")
    try:
        _assert_red(catalog, "PRODUCT-CATALOG:TRIGGER-SECURITY-INVOKER")
    finally:
        catalog.observer.rollback()
        _alter_function_security(catalog, schema_name, function_name, "INVOKER")


def test_null_trigger_function_acl_is_red(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """Migration が作り直した NULL ACL の PUBLIC EXECUTE を拒否する。"""
    catalog = provisioned_product_catalog
    schema_name, function_name = _migration_trigger_function(catalog)
    unapply_product_authz_ddl(catalog.applicator)
    try:
        config = Config(str(_BACKEND_ROOT / "alembic.ini"))
        command.downgrade(config, "base")
        command.upgrade(config, "head")

        with catalog.observer.cursor() as cursor:
            cursor.execute(
                """
                SELECT routine.proacl IS NULL
                FROM pg_catalog.pg_proc AS routine
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = routine.pronamespace
                WHERE namespace.nspname = %s
                  AND routine.proname = %s
                  AND routine.pronargs = 0
                """,
                (schema_name, function_name),
            )
            row = cursor.fetchone()
        catalog.observer.rollback()
        assert row == (True,)
        _assert_red(catalog, "PRODUCT-CATALOG:FUNCTION-ACL")
    finally:
        catalog.observer.rollback()
        apply_product_authz_ddl(catalog.applicator)
