"""製品認可カタログの exact-set 検査を実 PostgreSQL で検証する。"""

from __future__ import annotations

import json
import secrets
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql

from pitchlog.authz import product_catalog, product_provisioning
from pitchlog.authz.asset_spec import PRODUCT_SPEC
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


def test_extension_in_other_schema_is_red(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """Pgcrypto を宣言と異なるスキーマへ移すと検出する。"""
    catalog = provisioned_product_catalog
    assert catalog.asset["extensions"] == [
        {
            "extension_id": "pgcrypto",
            "extension_name": "pgcrypto",
            "schema_name": "authn_crypto",
        }
    ]
    privileged_oid = _bootstrap_superuser_oid(catalog)
    try:
        assert _inspect(catalog).ok
        with catalog.applicator.cursor() as cursor:
            cursor.execute("ALTER EXTENSION pgcrypto SET SCHEMA public")
        report = inspect_product_authz_catalog(
            catalog.applicator,
            privileged_role_oids=frozenset({privileged_oid}),
        )
        assert "PRODUCT-CATALOG:EXTENSIONS" in {
            violation.check_id for violation in report.violations
        }
    finally:
        catalog.observer.rollback()
        catalog.applicator.rollback()


def test_unlisted_table_acl_is_red(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """実カタログへ表 ACL を 1 件足すと資産との exact 照合が失敗する。"""
    catalog = provisioned_product_catalog
    with catalog.applicator.cursor() as cursor:
        cursor.execute("GRANT SELECT ON TABLE public.analysis_groups TO pitchlog_app")
    catalog.applicator.commit()
    try:
        _assert_red(catalog, "PRODUCT-CATALOG:TABLE-ACL")
    finally:
        catalog.observer.rollback()
        with catalog.applicator.cursor() as cursor:
            cursor.execute(
                "REVOKE SELECT ON TABLE public.analysis_groups FROM pitchlog_app"
            )
        catalog.applicator.commit()


def test_removed_role_after_new_application_is_red(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """ロールを 1 件消した試験用資産を新規適用して独立集合と照合する。"""
    catalog = provisioned_product_catalog
    removed_role = "pitchlog_management_fn_owner"
    root = tmp_path / "repository"
    repository_root = _BACKEND_ROOT.parent
    shutil.copytree(
        repository_root / PRODUCT_SPEC.asset_root, root / PRODUCT_SPEC.asset_root
    )
    asset_path = root / PRODUCT_SPEC.ddl_elements_path
    mutated_asset = json.loads(asset_path.read_text(encoding="utf-8"))
    mutated_asset["roles"] = [
        row for row in mutated_asset["roles"] if row["role_id"] != removed_role
    ]
    declared_function_grants = sum(
        grant["grantee"] == removed_role
        for row in mutated_asset["functions"]
        for grant in row["acl_expectations"]
    )
    assert declared_function_grants > 0
    for section in ("schemas", "functions"):
        for row in mutated_asset[section]:
            for field in ("acl_expectations", "revoked_acl_expectations"):
                row[field] = [
                    grant for grant in row[field] if grant["grantee"] != removed_role
                ]
    assert removed_role not in json.dumps(mutated_asset)
    asset_path.write_text(json.dumps(mutated_asset), encoding="utf-8")
    manifest_path = root / PRODUCT_SPEC.body_manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    role_entry = next(
        entry
        for entry in manifest["entries"]
        if entry["element_type"] == "role" and entry["element_id"] == removed_role
    )
    manifest["entries"].remove(role_entry)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (root / role_entry["path"]).unlink()
    for relative_path in (
        "databases/current_database.sql",
        "schemas/authz_private.sql",
        "schemas/public.sql",
        "schemas/authn.sql",
    ):
        body_path = root / PRODUCT_SPEC.body_directory / relative_path
        body = body_path.read_text(encoding="utf-8")
        assert ", pitchlog_management_fn_owner" in body
        body_path.write_text(
            body.replace(", pitchlog_management_fn_owner", ""), encoding="utf-8"
        )
    removed_function_grants = 0
    for entry in manifest["entries"]:
        if entry["element_type"] != "function":
            continue
        body_path = root / entry["path"]
        body = body_path.read_text(encoding="utf-8")
        lines = body.splitlines(keepends=True)
        retained = [
            line for line in lines if "TO pitchlog_management_fn_owner;" not in line
        ]
        removed_function_grants += len(lines) - len(retained)
        if len(retained) != len(lines):
            body_path.write_text("".join(retained), encoding="utf-8")
    assert removed_function_grants == declared_function_grants
    assert all(
        removed_role not in (root / entry["path"]).read_text(encoding="utf-8")
        for entry in manifest["entries"]
    )
    checker_path = root / PRODUCT_SPEC.body_checker_path
    checker_path.parent.mkdir(parents=True)
    checker_path.symlink_to(repository_root / PRODUCT_SPEC.body_checker_path)

    unapply_product_authz_ddl(catalog.applicator)
    mutated_applied = False
    try:
        with monkeypatch.context() as mutation:
            mutation.setattr(product_provisioning, "_REPOSITORY_ROOT", root)
            apply_product_authz_ddl(catalog.applicator)
        mutated_applied = True
        _assert_red(catalog, "PRODUCT-CATALOG:ROLES")
        with monkeypatch.context() as mutation:
            mutation.setattr(
                product_catalog, "_load_product_asset", lambda: mutated_asset
            )
            with pytest.raises(
                product_catalog.ProductCatalogError, match="独立の意味契約"
            ):
                _inspect(catalog)
    finally:
        catalog.observer.rollback()
        if mutated_applied:
            with monkeypatch.context() as mutation:
                mutation.setattr(product_provisioning, "_REPOSITORY_ROOT", root)
                unapply_product_authz_ddl(catalog.applicator)
        apply_product_authz_ddl(catalog.applicator)


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


def test_authn_definers_have_independent_catalog_shape(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """認証関数の署名・所有者・実行モード・固定 search_path を実カタログで照合する。"""
    from pitchlog.authz.product_authn_contract import (
        AUTHN_FUNCTION_GRANTEES,
        AUTHN_OWNER,
    )

    catalog = provisioned_product_catalog
    try:
        with catalog.observer.cursor() as cursor:
            cursor.execute(
                """
                SELECT routine.proname,
                       pg_catalog.oidvectortypes(routine.proargtypes),
                       owner.rolname, routine.prosecdef,
                       routine.proconfig, language.lanname
                FROM pg_catalog.pg_proc AS routine
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = routine.pronamespace
                JOIN pg_catalog.pg_roles AS owner ON owner.oid = routine.proowner
                JOIN pg_catalog.pg_language AS language
                  ON language.oid = routine.prolang
                WHERE namespace.nspname = 'authn'
                ORDER BY 1, 2
                """
            )
            rows = cursor.fetchall()
        assert {(row[0], row[1]) for row in rows} == set(AUTHN_FUNCTION_GRANTEES)
        for _, _, owner, is_definer, settings, language in rows:
            assert owner == AUTHN_OWNER
            assert is_definer is True
            assert language == "plpgsql"
            assert settings is not None
            assert tuple(value.replace(" ", "") for value in settings) == (
                "search_path=pg_catalog,pg_temp",
            )
    finally:
        catalog.observer.rollback()


def test_pgcrypto_public_execute_mutation_is_red(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """拡張メンバー関数への PUBLIC EXECUTE を実カタログの検査で拒否する。"""
    catalog = provisioned_product_catalog
    try:
        with catalog.applicator.cursor() as cursor:
            cursor.execute(
                "GRANT EXECUTE ON FUNCTION authn_crypto.crypt(text, text) TO PUBLIC"
            )
        catalog.applicator.commit()
        _assert_red(catalog, "PRODUCT-CATALOG:PGCRYPTO-MEMBER-ACL-INDEPENDENT")
    finally:
        catalog.observer.rollback()
        catalog.applicator.rollback()
        with catalog.applicator.cursor() as cursor:
            cursor.execute(
                "REVOKE EXECUTE ON FUNCTION authn_crypto.crypt(text, text) FROM PUBLIC"
            )
        catalog.applicator.commit()
