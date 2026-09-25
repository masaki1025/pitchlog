"""制御資源の補助関数・ポリシーと製品資産全体を検査する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitchlog.authz.asset_spec import PRODUCT_SPEC
from pitchlog.authz.ddl import generate_authz_ddl
from pitchlog.authz.product_control_access import (
    CONTROL_PROFILE,
    CONTROL_TABLE_IDS,
    HELPER_DEPENDENCY_COLUMNS,
    HELPER_FUNCTION_ID,
    HELPER_OWNER_ROLE_ID,
    build_control_policy_declaration,
    build_helper_column_acl_declaration,
    build_membership_helper_declaration,
    generate_control_policy_sql,
    generate_helper_column_acl_sql,
    generate_membership_helper_sql,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_CHECKER = _REPOSITORY_ROOT / "scripts/check_authz_catalog.py"
_MIGRATION_VERSIONS = Path("backend/migrations/versions")
_PROVISIONAL_CONTRACT = Path("contracts/tenant_boundary/runtime-authz-contract.json")
_EXPECTED_DEPENDENCY_COLUMNS = frozenset(
    {
        ("tenants", "id"),
        ("tenants", "enabled"),
        ("analysis_groups", "id"),
        ("analysis_groups", "status"),
        ("group_memberships", "group_id"),
        ("group_memberships", "tenant_id"),
        ("group_memberships", "role"),
        ("group_memberships", "status"),
    }
)
_EXPECTED_CONTROL_EXPRESSIONS = {
    "analysis_groups": "authz_private.tenant_has_effective_membership(id, false)",
    "group_memberships": (
        "authz_private.tenant_has_effective_membership(group_id, false)"
    ),
    "sharing_grants": (
        "EXISTS (SELECT 1 FROM public.group_memberships AS membership "
        "WHERE membership.id = sharing_grants.membership_id AND "
        "authz_private.tenant_has_effective_membership("
        "membership.group_id, false))"
    ),
    "group_invitations": (
        "authz_private.tenant_has_effective_membership(group_id, true)"
    ),
}


def _load_catalog_checker() -> Any:
    """静的検査を独立したモジュール名で読み込む。"""
    module_spec = importlib.util.spec_from_file_location(
        "check_authz_catalog_product_control_access_under_test",
        _CATALOG_CHECKER,
    )
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = module
    module_spec.loader.exec_module(module)
    return module


_catalog_checker = _load_catalog_checker()


def _read_json_object(path: Path) -> dict[str, Any]:
    """JSON objectを読み、試験入力の形を確定する。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _product_asset() -> dict[str, Any]:
    """製品DDL資産を読む。"""
    return _read_json_object(_REPOSITORY_ROOT / PRODUCT_SPEC.ddl_elements_path)


def _validate_product_asset(
    asset: dict[str, Any],
    root: Path = _REPOSITORY_ROOT,
) -> dict[str, object]:
    """製品DDL資産を静的検査へ渡す。"""
    return _catalog_checker.validate_ddl_elements(asset, root, PRODUCT_SPEC)


def _copy_static_inputs(root: Path) -> None:
    """製品資産全体の静的検査に必要な入力を複製する。"""
    paths = (
        Path("contracts/db/schema-manifest.json"),
        Path("contracts/authz/product/table-classification.json"),
        Path("contracts/authz/product/exposure-facts.json"),
        PRODUCT_SPEC.ddl_elements_path,
        _PROVISIONAL_CONTRACT,
    )
    for relative_path in paths:
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_REPOSITORY_ROOT / relative_path, destination)
    shutil.copytree(
        _REPOSITORY_ROOT / PRODUCT_SPEC.body_directory,
        root / PRODUCT_SPEC.body_directory,
    )
    shutil.copytree(
        _REPOSITORY_ROOT / _MIGRATION_VERSIONS,
        root / _MIGRATION_VERSIONS,
    )


def _helper_row(asset: dict[str, Any]) -> dict[str, Any]:
    """実効参加補助関数の宣言を返す。"""
    return next(
        row for row in asset["functions"] if row["function_id"] == HELPER_FUNCTION_ID
    )


def _mutate_remove_pg_temp(asset: dict[str, Any]) -> None:
    """補助関数のsearch_pathからpg_tempを消す。"""
    _helper_row(asset)["search_path"] = ["pg_catalog"]


def _grant_helper_execute(asset: dict[str, Any], grantee: str) -> None:
    """補助関数へ不正なEXECUTE付与を足す。"""
    _helper_row(asset)["acl_expectations"].append(
        {"grantee": grantee, "privilege": "EXECUTE", "grantable": False}
    )


def _mutate_public_execute(asset: dict[str, Any]) -> None:
    """PUBLICへ補助関数のEXECUTEを与える。"""
    _grant_helper_execute(asset, "PUBLIC")


def _mutate_app_execute(asset: dict[str, Any]) -> None:
    """アプリ用ロールへ補助関数のEXECUTEを与える。"""
    _grant_helper_execute(asset, "pitchlog_app")


def _mutate_invitation_without_admin(asset: dict[str, Any]) -> None:
    """招待ポリシーから管理者要求を外す。"""
    policy = next(
        row for row in asset["policies"] if row["table_id"] == "group_invitations"
    )
    policy["using_expression"] = policy["using_expression"].replace("true", "false")


def _mutate_owner_table_select(asset: dict[str, Any]) -> None:
    """補助関数所有者へ表単位のSELECTを与える。"""
    asset["acl_expectations"].append(
        {
            "acl_id": "ACL:tenants:pitchlog_shared_fn_owner",
            "object_kind": "table",
            "object_schema": "public",
            "object_id": "tenants",
            "profile": "helper_dependency",
            "grantee_role_id": HELPER_OWNER_ROLE_ID,
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        }
    )


def _mutate_add_unused_column(asset: dict[str, Any]) -> None:
    """補助関数が使わない列のSELECTを足す。"""
    asset["column_acl_expectations"].append(
        {
            "expectation_id": (
                "COLUMN-ACL:public:tenants:name:pitchlog_shared_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "tenants",
            "column_id": "name",
            "grantee_role_id": HELPER_OWNER_ROLE_ID,
            "privilege_ids": ["SELECT"],
            "grant_option": False,
            "function_id": HELPER_FUNCTION_ID,
        }
    )


def _mutate_remove_required_column(asset: dict[str, Any]) -> None:
    """補助関数に必要な列のSELECTを1件消す。"""
    asset["column_acl_expectations"].pop()


def test_membership_helper_and_control_policies_match_design() -> None:
    """補助関数の属性・依存列と制御資源4表のポリシーが完全一致する。"""
    asset = _product_asset()
    _validate_product_asset(asset)

    expected_helper = {
        "function_id": (
            "FUNCTION:authz_private:tenant_has_effective_membership(uuid, boolean)"
        ),
        "schema_name": "authz_private",
        "function_name": "tenant_has_effective_membership",
        "identity_args": "uuid, boolean",
        "function_kind": "rls_helper",
        "owner_role_id": "pitchlog_shared_fn_owner",
        "language": "sql",
        "returns": "boolean",
        "security_mode": "definer",
        "volatility": "stable",
        "search_path": ["pg_catalog", "pg_temp"],
        "acl_expectations": [],
        "revoked_acl_expectations": [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
            {
                "grantee": "pitchlog_app",
                "privilege": "EXECUTE",
                "grantable": False,
            },
        ],
    }
    assert _helper_row(asset) == expected_helper
    assert build_membership_helper_declaration() == expected_helper
    public_schema = next(
        row for row in asset["schemas"] if row["schema_id"] == "public"
    )
    assert {
        (row["grantee"], row["privilege"], row["grantable"])
        for row in public_schema["acl_expectations"]
        if row["grantee"] == HELPER_OWNER_ROLE_ID
    } == {(HELPER_OWNER_ROLE_ID, "USAGE", False)}

    column_acls = {
        row["expectation_id"]: row for row in asset["column_acl_expectations"]
    }
    assert frozenset(HELPER_DEPENDENCY_COLUMNS) == _EXPECTED_DEPENDENCY_COLUMNS
    expected_column_acls = {
        declaration["expectation_id"]: declaration
        for table_id, column_id in _EXPECTED_DEPENDENCY_COLUMNS
        for declaration in [build_helper_column_acl_declaration(table_id, column_id)]
    }
    assert column_acls == expected_column_acls
    assert not any(
        row["grantee_role_id"] == HELPER_OWNER_ROLE_ID
        for row in asset["acl_expectations"]
    )

    control_policies = {
        row["table_id"]: row
        for row in asset["policies"]
        if row["profile"] == CONTROL_PROFILE
    }
    assert set(CONTROL_TABLE_IDS) == set(_EXPECTED_CONTROL_EXPRESSIONS)
    assert set(control_policies) == set(_EXPECTED_CONTROL_EXPRESSIONS)
    assert control_policies == {
        table_id: build_control_policy_declaration(table_id)
        for table_id in _EXPECTED_CONTROL_EXPRESSIONS
    }
    assert {
        table_id: row["using_expression"] for table_id, row in control_policies.items()
    } == _EXPECTED_CONTROL_EXPRESSIONS
    assert all(
        row["object_id"] not in CONTROL_TABLE_IDS
        for row in asset["acl_expectations"]
        if row["grantee_role_id"] == "pitchlog_app"
    )

    statements = generate_authz_ddl(_REPOSITORY_ROOT, PRODUCT_SPEC)
    statement_positions = {
        (statement.element_type, statement.element_id): index
        for index, statement in enumerate(statements)
    }
    assert statement_positions[("function", HELPER_FUNCTION_ID)] < min(
        statement_positions[("policy", f"POLICY:{table_id}:{CONTROL_PROFILE}")]
        for table_id in _EXPECTED_CONTROL_EXPRESSIONS
    )
    sql_by_element = {
        (statement.element_type, statement.element_id): statement.sql
        for statement in statements
    }
    helper_sql = sql_by_element[("function", HELPER_FUNCTION_ID)]
    assert helper_sql == generate_membership_helper_sql()
    assert "SECURITY DEFINER" in helper_sql
    assert "STABLE" in helper_sql
    assert "SET search_path = pg_catalog, pg_temp" in helper_sql
    assert "FROM public.analysis_groups" in helper_sql
    assert "JOIN public.group_memberships" in helper_sql
    assert "JOIN public.tenants" in helper_sql
    assert "effective_group.status = 'active'" in helper_sql
    assert "membership.status = 'active'" in helper_sql
    assert "member_tenant.enabled" in helper_sql
    assert "membership.role = 'admin'" in helper_sql
    assert "SELECT COALESCE(" in helper_sql and "false" in helper_sql
    assert "pg_catalog.coalesce" not in helper_sql
    assert helper_sql.index("CREATE OR REPLACE FUNCTION") < helper_sql.index(
        "REVOKE ALL PRIVILEGES"
    )

    for table_id in _EXPECTED_CONTROL_EXPRESSIONS:
        policy_id = f"POLICY:{table_id}:{CONTROL_PROFILE}"
        assert sql_by_element[("policy", policy_id)] == generate_control_policy_sql(
            table_id
        )
    for table_id, column_id in _EXPECTED_DEPENDENCY_COLUMNS:
        declaration = build_helper_column_acl_declaration(table_id, column_id)
        expectation_id = str(declaration["expectation_id"])
        assert sql_by_element[("column_acl_expectation", expectation_id)] == (
            generate_helper_column_acl_sql(table_id, column_id)
        )


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_mutate_remove_pg_temp, id="pg-temp-removed"),
        pytest.param(_mutate_public_execute, id="public-execute"),
        pytest.param(_mutate_app_execute, id="app-execute"),
        pytest.param(_mutate_invitation_without_admin, id="admin-not-required"),
        pytest.param(_mutate_owner_table_select, id="owner-table-select"),
        pytest.param(_mutate_add_unused_column, id="unused-column"),
        pytest.param(_mutate_remove_required_column, id="required-column-removed"),
    ],
)
def test_control_access_declaration_mutations_are_rejected(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    """正常資産を確認後、補助関数・ポリシー・権限の変異を拒否する。"""
    asset = _product_asset()
    _validate_product_asset(asset)
    mutated = copy.deepcopy(asset)
    mutate(mutated)

    with pytest.raises(_catalog_checker.CatalogError):
        _validate_product_asset(mutated)


@pytest.mark.parametrize(
    "condition",
    [
        pytest.param("AND effective_group.status = 'active'\n", id="group-active"),
        pytest.param("AND member_tenant.enabled\n", id="tenant-enabled"),
        pytest.param(
            "AND (NOT p_require_admin OR membership.role = 'admin')\n",
            id="admin-role",
        ),
    ],
)
def test_removing_helper_condition_from_body_is_rejected(
    tmp_path: Path,
    condition: str,
) -> None:
    """正常bodyを確認後、実効参加の必須条件欠落を拒否する。"""
    root = tmp_path / "repository"
    _copy_static_inputs(root)
    asset = _product_asset()
    _validate_product_asset(asset, root)

    body_path = (
        root / PRODUCT_SPEC.body_directory / "functions" / f"{HELPER_FUNCTION_ID}.sql"
    )
    text = body_path.read_text(encoding="utf-8")
    assert condition in text
    body_path.write_text(text.replace(condition, "", 1), encoding="utf-8")

    with pytest.raises(_catalog_checker.CatalogError, match="生成結果と不一致"):
        _validate_product_asset(asset, root)


def test_schema_qualified_coalesce_in_helper_body_is_rejected(
    tmp_path: Path,
) -> None:
    """正常bodyを確認後、SQL構文COALESCEの誤った修飾を拒否する。"""
    root = tmp_path / "repository"
    _copy_static_inputs(root)
    asset = _product_asset()
    _validate_product_asset(asset, root)

    body_path = (
        root / PRODUCT_SPEC.body_directory / "functions" / f"{HELPER_FUNCTION_ID}.sql"
    )
    text = body_path.read_text(encoding="utf-8")
    assert text.count("SELECT COALESCE(") == 1
    body_path.write_text(
        text.replace("SELECT COALESCE(", "SELECT pg_catalog.coalesce(", 1),
        encoding="utf-8",
    )

    with pytest.raises(_catalog_checker.CatalogError, match="生成結果と不一致"):
        _validate_product_asset(asset, root)


def test_staged_protected_targets_are_the_declared_extension_only() -> None:
    """Staged保護対象が暫定契約と理由付き追加分の和へ完全一致する。"""
    asset = _product_asset()
    _validate_product_asset(asset)
    _catalog_checker._validate_product_protected_targets(asset, _REPOSITORY_ROOT)

    additions = asset["provisional_contract_additions"]
    assert len(additions) == 6
    assert {row["reason"] for row in additions} == {
        "provisional_contract_gap",
        "product_authz_private",
        "product_authz_helper",
    }

    mutated = copy.deepcopy(asset)
    mutated["schemas"].append(
        {
            "schema_id": "undeclared_private",
            "schema_name": "undeclared_private",
        }
    )
    with pytest.raises(_catalog_checker.CatalogError, match="宣言済み追加分"):
        _catalog_checker._validate_product_protected_targets(
            mutated,
            _REPOSITORY_ROOT,
        )


@pytest.mark.parametrize(
    "target",
    [
        pytest.param("manifest", id="manifest-entry"),
        pytest.param("body", id="body-file"),
        pytest.param("element", id="ddl-element"),
    ],
)
def test_product_element_manifest_and_body_must_match_exactly(
    tmp_path: Path,
    target: str,
) -> None:
    """正常な三者対応を確認後、いずれか1件のずれを拒否する。"""
    root = tmp_path / "repository"
    _copy_static_inputs(root)
    asset = _product_asset()
    _validate_product_asset(asset, root)
    _catalog_checker._validate_product_asset_correspondence(asset, root)

    if target == "manifest":
        manifest_path = root / PRODUCT_SPEC.body_manifest_path
        manifest = _read_json_object(manifest_path)
        manifest["entries"] = [
            entry
            for entry in manifest["entries"]
            if entry["element_id"] != HELPER_FUNCTION_ID
        ]
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    elif target == "body":
        body_path = (
            root
            / PRODUCT_SPEC.body_directory
            / "functions"
            / f"{HELPER_FUNCTION_ID}.sql"
        )
        body_path.unlink()
    else:
        asset = copy.deepcopy(asset)
        asset["functions"] = [
            row
            for row in asset["functions"]
            if row["function_id"] != HELPER_FUNCTION_ID
        ]

    with pytest.raises(_catalog_checker.CatalogError):
        _catalog_checker._validate_product_asset_correspondence(asset, root)
