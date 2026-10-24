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
from test_authz_runtime_contract_repository import product_spec_for_repository

from pitchlog.authz.ddl import generate_authz_ddl
from pitchlog.authz.product_control_access import (
    CONTROL_PROFILE,
    CONTROL_TABLE_IDS,
    HELPER_FUNCTION_ID,
    HELPER_OWNER_ROLE_ID,
    build_control_policy_declaration,
    build_helper_column_acl_declaration,
    build_membership_helper_declaration,
    generate_control_policy_sql,
    generate_function_owner_column_acl_sql,
    generate_helper_column_acl_sql,
    generate_membership_helper_sql,
    is_forbidden_rg1_table_acl,
    is_rg1_singleton_update_acl,
)
from pitchlog.authz.product_table_access import generate_function_owner_table_acl_sql
from pitchlog.authz.runtime_contract_state import (
    RuntimeContractState,
    evaluate_repository,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PRODUCT_SPEC = product_spec_for_repository(_REPOSITORY_ROOT)
_CATALOG_CHECKER = _REPOSITORY_ROOT / "scripts/check_authz_catalog.py"
_MIGRATION_VERSIONS = Path("backend/migrations/versions")
_RUNTIME_CONTRACT = Path("contracts/tenant_boundary/runtime-authz-contract.json")
_RUNTIME_CONTRACT_MODULE = Path("backend/src/pitchlog/authz/runtime_contract.py")
_RUNTIME_CONTRACT_STATE, _RUNTIME_CONTRACT_VIOLATIONS = evaluate_repository(
    _REPOSITORY_ROOT
)
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


def _rg1_singleton_acl() -> dict[str, object]:
    """RG1の承認済み列権限だけを表す候補宣言を返す。"""
    return {
        "expectation_id": (
            "COLUMN-ACL:public:rg1_restore_gate:singleton_id:pitchlog_rg1_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "rg1_restore_gate",
        "column_id": "singleton_id",
        "grantee_role_id": "pitchlog_rg1_fn_owner",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
        "function_id": "FUNCTION:rg1_api:rg1_assert_open_before_commit(uuid)",
    }


def test_rg1_singleton_update_acl_is_column_scoped() -> None:
    """RG1の確定前関数にだけ単一列SELECT・UPDATEを生成する。"""
    declaration = _rg1_singleton_acl()
    assert is_rg1_singleton_update_acl(declaration)
    assert generate_function_owner_column_acl_sql(declaration) == (
        "-- ELEMENT-TYPE: column_acl_expectation\n"
        "-- ELEMENT-ID: "
        "COLUMN-ACL:public:rg1_restore_gate:singleton_id:pitchlog_rg1_fn_owner\n"
        "\n"
        "GRANT SELECT (singleton_id), UPDATE (singleton_id) "
        "ON TABLE public.rg1_restore_gate TO pitchlog_rg1_fn_owner;\n"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("object_id", "other_table"),
        ("column_id", "state"),
        ("grantee_role_id", "pitchlog_app"),
        ("object_schema", "other_schema"),
        ("function_id", "FUNCTION:rg1_api:rg1_read_open(uuid)"),
        ("privilege_ids", ["UPDATE"]),
        ("privilege_ids", ["SELECT", "UPDATE", "DELETE"]),
        ("grant_option", True),
    ),
)
def test_rg1_singleton_update_acl_rejects_other_targets(
    field: str, value: object
) -> None:
    """表・列・owner・関数・権限が一つでも異なればUPDATEを拒否する。"""
    declaration = _rg1_singleton_acl()
    declaration[field] = value
    assert not is_rg1_singleton_update_acl(declaration)
    with pytest.raises(ValueError):
        generate_function_owner_column_acl_sql(declaration)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("object_id", "other_table"),
        ("column_id", "state"),
        ("grantee_role_id", "pitchlog_app"),
        ("object_schema", "other_schema"),
        ("function_id", "FUNCTION:rg1_api:rg1_read_open(uuid)"),
        ("privilege_ids", ["UPDATE"]),
        ("privilege_ids", ["SELECT", "UPDATE", "DELETE"]),
        ("grant_option", True),
    ),
)
def test_catalog_checker_rejects_rg1_update_acl_mutations(
    field: str, value: object
) -> None:
    """製品catalog検査器もRG1の許可組合せ以外を拒否する。"""
    asset = _product_asset()
    singleton_acl = next(
        row
        for row in asset["column_acl_expectations"]
        if row.get("expectation_id") == _rg1_singleton_acl()["expectation_id"]
    )
    _catalog_checker._validate_product_membership_helper(
        asset, _REPOSITORY_ROOT, RuntimeContractState.PROVISIONAL
    )

    singleton_acl[field] = value
    with pytest.raises(_catalog_checker.CatalogError):
        _catalog_checker._validate_product_membership_helper(
            asset, _REPOSITORY_ROOT, RuntimeContractState.PROVISIONAL
        )


@pytest.mark.parametrize(
    ("table_id", "owner_role_id"),
    (
        ("tenants", "pitchlog_rg1_fn_owner"),
        ("rg1_restore_gate", "pitchlog_management_fn_owner"),
        ("games", "pitchlog_rg1_control_owner"),
        ("games", "pitchlog_rg1_control_actor"),
        ("games", "pitchlog_ledger_identity_owner"),
        ("games", "pitchlog_ledger_identity_probe"),
    ),
)
def test_catalog_checker_rejects_rg1_table_acl(
    table_id: str, owner_role_id: str
) -> None:
    """RG1表または専用ownerへの表権限を列ACLの迂回口にしない。"""
    asset = _product_asset()
    asset["policies"] = [
        row for row in asset["policies"] if row["role_ids"] != ["pitchlog_owner"]
    ]
    rg1_function = copy.deepcopy(
        next(row for row in asset["functions"] if row["function_kind"] == "definer")
    )
    rg1_function["function_id"] = "FUNCTION:rg1_api:synthetic()"
    rg1_function["owner_role_id"] = owner_role_id
    asset["functions"].append(rg1_function)
    acl: dict[str, object] = {
        "acl_id": f"ACL:{table_id}:{owner_role_id}",
        "object_kind": "table",
        "object_schema": "public",
        "object_id": table_id,
        "profile": "function_dependency",
        "grantee_role_id": owner_role_id,
        "privilege_ids": ["UPDATE"],
        "grant_option": False,
    }
    assert is_forbidden_rg1_table_acl(acl)
    with pytest.raises(ValueError, match="RG1状態表"):
        generate_function_owner_table_acl_sql(acl)
    asset["acl_expectations"].append(acl)
    with pytest.raises(_catalog_checker.CatalogError, match="RG1状態表"):
        _catalog_checker._validate_product_table_access_expectations(
            asset, _REPOSITORY_ROOT, RuntimeContractState.PROVISIONAL
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("owner", "pitchlog_app"),
        (
            "acl_expectations",
            [
                {"grantee": "pitchlog_app", "privilege": "USAGE", "grantable": False},
                {"grantee": "pitchlog_app", "privilege": "CREATE", "grantable": False},
            ],
        ),
        ("revoked_acl_expectations", []),
    ),
)
def test_rg1_api_schema_rejects_owner_and_acl_expansion(
    field: str, value: object
) -> None:
    """RG1 schemaの所有者とCREATE/USAGEをexact集合から広げない。"""
    asset = _product_asset()
    schema = next(row for row in asset["schemas"] if row["schema_id"] == "rg1_api")
    schema[field] = value
    with pytest.raises(_catalog_checker.CatalogError):
        _catalog_checker._validate_product_schema_expectations(
            asset["schemas"], authn_enabled=True
        )


def test_rg1_table_requires_dedicated_schema() -> None:
    """状態表を残したまま専用関数schemaを省くことを拒否する。"""
    asset = _product_asset()
    asset["schemas"] = [
        row for row in asset["schemas"] if row["schema_id"] != "rg1_api"
    ]
    with pytest.raises(_catalog_checker.CatalogError):
        _catalog_checker._validate_product_schema_expectations(
            asset["schemas"], authn_enabled=True, rg1_required=True
        )


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
        _RUNTIME_CONTRACT,
        _RUNTIME_CONTRACT_MODULE,
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
    assert {
        (row["object_id"], row["column_id"])
        for row in column_acls.values()
        if row["function_id"] == HELPER_FUNCTION_ID
    } == _EXPECTED_DEPENDENCY_COLUMNS
    expected_column_acls = {
        declaration["expectation_id"]: declaration
        for table_id, column_id in _EXPECTED_DEPENDENCY_COLUMNS
        for declaration in [build_helper_column_acl_declaration(table_id, column_id)]
    }
    assert {
        key: row
        for key, row in column_acls.items()
        if row["function_id"] == HELPER_FUNCTION_ID
    } == expected_column_acls
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


def test_additional_declared_helper_column_acl_is_accepted(tmp_path: Path) -> None:
    """補助関数の列 ACL 件数を資産宣言から導出する。"""
    root = tmp_path / "repository"
    _copy_static_inputs(root)
    asset = _product_asset()
    declaration = build_helper_column_acl_declaration("tenants", "name")
    asset["column_acl_expectations"].append(declaration)
    path = (
        PRODUCT_SPEC.body_directory
        / "column_acl_expectations"
        / f"{declaration['expectation_id']}.sql"
    )
    (root / path).write_text(
        generate_helper_column_acl_sql("tenants", "name"), encoding="utf-8"
    )
    manifest_path = root / PRODUCT_SPEC.body_manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["entries"].append(
        {
            "path": path.as_posix(),
            "element_type": "column_acl_expectation",
            "element_id": declaration["expectation_id"],
        }
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert _validate_product_asset(asset, root)["product_role_count"] == len(
        asset["roles"]
    )


def test_protected_targets_match_the_repository_state() -> None:
    """保護対象を未発効の和または製品資産の導出値へ完全照合する。"""
    asset = _product_asset()
    _validate_product_asset(asset)
    assert _RUNTIME_CONTRACT_VIOLATIONS == set()
    _catalog_checker._validate_product_protected_targets_for_state(
        asset,
        _REPOSITORY_ROOT,
        _RUNTIME_CONTRACT_STATE,
    )

    if _RUNTIME_CONTRACT_STATE is RuntimeContractState.PENDING:
        additions = asset["provisional_contract_additions"]
        assert len(additions) == 6
        assert {row["reason"] for row in additions} == {
            "provisional_contract_gap",
            "product_authz_private",
            "product_authz_helper",
        }
    else:
        assert _RUNTIME_CONTRACT_STATE is RuntimeContractState.PRODUCT
        assert "provisional_contract_additions" not in asset

    mutated = copy.deepcopy(asset)
    mutated["schemas"].append(
        {
            "schema_id": "undeclared_private",
            "schema_name": "undeclared_private",
        }
    )
    with pytest.raises(_catalog_checker.CatalogError):
        _catalog_checker._validate_product_protected_targets_for_state(
            mutated,
            _REPOSITORY_ROOT,
            _RUNTIME_CONTRACT_STATE,
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


@pytest.mark.parametrize(
    "column,privileges",
    (
        ("singleton_id", ["SELECT"]),
        ("state", ["SELECT", "UPDATE"]),
    ),
)
def test_rg1_control_owner_has_only_its_exact_column_acl(
    column: str,
    privileges: list[str],
) -> None:
    """制御ownerだけのsingleton SELECT/state UPDATEを分離して検査する。"""
    from pitchlog.authz.product_control_access import (
        generate_function_owner_column_acl_sql,
        is_rg1_control_column_acl,
    )

    declaration: dict[str, object] = {
        "expectation_id": (
            f"COLUMN-ACL:public:rg1_restore_gate:{column}:pitchlog_rg1_control_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "rg1_restore_gate",
        "column_id": column,
        "grantee_role_id": "pitchlog_rg1_control_owner",
        "privilege_ids": privileges,
        "grant_option": False,
        "function_id": "FUNCTION:rg1_control:close_gate()",
    }
    assert is_rg1_control_column_acl(declaration)
    sql = generate_function_owner_column_acl_sql(declaration)
    assert "TO pitchlog_rg1_control_owner;" in sql
    assert ("UPDATE (state)" in sql) is (column == "state")
    for field, value in (
        ("grantee_role_id", "pitchlog_rg1_fn_owner"),
        ("function_id", "FUNCTION:rg1_api:rg1_assert_open_before_commit(uuid)"),
        ("object_id", "games"),
        ("grant_option", 0),
    ):
        mutated = {**declaration, field: value}
        assert not is_rg1_control_column_acl(mutated)


def test_old_rg1_reader_cannot_acquire_state_update_through_control_extension() -> None:
    """新制御能力を旧read ownerや他tableへ転用しない。"""
    from pitchlog.authz.product_control_access import (
        generate_function_owner_column_acl_sql,
    )

    declaration: dict[str, object] = {
        "expectation_id": (
            "COLUMN-ACL:public:rg1_restore_gate:state:pitchlog_rg1_fn_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "rg1_restore_gate",
        "column_id": "state",
        "grantee_role_id": "pitchlog_rg1_fn_owner",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
        "function_id": "FUNCTION:rg1_api:rg1_assert_open_before_commit(uuid)",
    }
    with pytest.raises(ValueError):
        generate_function_owner_column_acl_sql(declaration)


@pytest.mark.parametrize(
    "role_id",
    (
        "pitchlog_rg1_control_owner",
        "pitchlog_rg1_control_actor",
        "pitchlog_ledger_identity_owner",
        "pitchlog_ledger_identity_probe",
    ),
)
@pytest.mark.parametrize(
    "table,column",
    (
        ("admin_credentials", "password_hash"),
        ("games", "id"),
    ),
)
def test_rg1_new_principals_cannot_acquire_business_column_access(
    role_id: str,
    table: str,
    column: str,
) -> None:
    """新観測/制御主体の業務列SELECTを資産とSQL生成の双方で拒否する。"""
    function_id = "FUNCTION:rg1_control:synthetic_restricted()"
    declaration: dict[str, object] = {
        "expectation_id": f"COLUMN-ACL:public:{table}:{column}:{role_id}",
        "object_kind": "column",
        "object_schema": "public",
        "object_id": table,
        "column_id": column,
        "grantee_role_id": role_id,
        "privilege_ids": ["SELECT"],
        "grant_option": False,
        "function_id": function_id,
    }
    with pytest.raises(ValueError, match="業務列ACL|固定2列"):
        generate_function_owner_column_acl_sql(declaration)
    asset = _product_asset()
    function = copy.deepcopy(
        next(row for row in asset["functions"] if row["function_kind"] == "definer")
    )
    function["function_id"] = function_id
    function["owner_role_id"] = role_id
    asset["functions"].append(function)
    asset["column_acl_expectations"].append(declaration)
    with pytest.raises(_catalog_checker.CatalogError, match="業務列ACL|固定2列"):
        _catalog_checker._validate_product_membership_helper(
            asset,
            _REPOSITORY_ROOT,
            RuntimeContractState.PROVISIONAL,
        )


def _fresh_epoch_acl() -> dict[str, object]:
    """既承認の初回epoch setterだけが持つ1列ACLを返す。"""
    return {
        "expectation_id": (
            "COLUMN-ACL:public:rg1_restore_gate:recovery_generation:"
            "pitchlog_rg1_control_owner"
        ),
        "object_kind": "column",
        "object_schema": "public",
        "object_id": "rg1_restore_gate",
        "column_id": "recovery_generation",
        "grantee_role_id": "pitchlog_rg1_control_owner",
        "privilege_ids": ["SELECT", "UPDATE"],
        "grant_option": False,
        "function_id": "FUNCTION:rg1_control:bind_initial_fresh_epoch(bigint)",
    }


def test_fresh_epoch_acl_generates_only_the_fixed_epoch_column() -> None:
    """有限受理済みepoch ACLを実SQLへ生成し、旧state列を拡張しない。"""
    from pitchlog.authz.product_control_access import is_rg1_control_column_acl

    declaration = _fresh_epoch_acl()
    assert is_rg1_control_column_acl(declaration)
    sql = generate_function_owner_column_acl_sql(declaration)
    assert "GRANT SELECT (recovery_generation), UPDATE (recovery_generation)" in sql
    assert "ON TABLE public.rg1_restore_gate TO pitchlog_rg1_control_owner;" in sql
    assert "UPDATE (state)" not in sql


@pytest.mark.parametrize(
    "field,value",
    (
        ("function_id", "FUNCTION:rg1_control:close_gate()"),
        ("grantee_role_id", "pitchlog_initial_actor"),
        ("object_id", "games"),
        ("column_id", "state"),
        ("privilege_ids", ["SELECT"]),
        ("grant_option", 0),
    ),
)
def test_fresh_epoch_acl_rejects_other_owners_functions_and_columns(
    field: str,
    value: object,
) -> None:
    """新1列権限を別関数/actor/旧列/緩いbool値へ流用させない。"""
    declaration = {**_fresh_epoch_acl(), field: value}
    with pytest.raises(ValueError):
        generate_function_owner_column_acl_sql(declaration)
