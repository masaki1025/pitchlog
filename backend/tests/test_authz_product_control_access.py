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
    # 現PRODUCTの全policy/roleを保ち、表ACL1件だけを拒否対象にする。
    _catalog_checker._validate_product_table_access_expectations(
        asset, _REPOSITORY_ROOT, RuntimeContractState.PRODUCT
    )
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
            asset, _REPOSITORY_ROOT, RuntimeContractState.PRODUCT
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
        Path("backend/src/pitchlog/recording_rights/rg1_lifecycle.sql"),
        Path("backend/src/pitchlog/durable_rights_ledger/business_identity.sql"),
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
        row
        for row in asset["functions"]
        if row.get("function_id") == HELPER_FUNCTION_ID
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
        if row.get("function_id") == HELPER_FUNCTION_ID
    } == _EXPECTED_DEPENDENCY_COLUMNS
    expected_column_acls = {
        declaration["expectation_id"]: declaration
        for table_id, column_id in _EXPECTED_DEPENDENCY_COLUMNS
        for declaration in [build_helper_column_acl_declaration(table_id, column_id)]
    }
    assert {
        key: row
        for key, row in column_acls.items()
        if row.get("function_id") == HELPER_FUNCTION_ID
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

    with pytest.raises(_catalog_checker.CatalogError) as error:
        _catalog_checker._validate_product_asset_correspondence(asset, root)
    if target == "body":
        missing_body = (
            PRODUCT_SPEC.body_directory / "functions" / f"{HELPER_FUNCTION_ID}.sql"
        )
        assert str(error.value).startswith(f"製品body[{missing_body}]を読めない:")
    else:
        assert str(error.value) == (
            "製品DDL要素・manifest・bodyファイルがexact-set不一致"
        )


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


def _fresh_epoch_unapplication(declaration: dict[str, object]) -> str | None:
    """実provisioningの構造化ACL撤去経路へ渡す。"""
    from pathlib import PurePosixPath

    from pitchlog.authz import product_provisioning
    from pitchlog.authz.ddl import DDLStatement

    expectation_id = str(declaration["expectation_id"])
    element = product_provisioning._ProductElement(
        element_type="column_acl_expectation",
        element_id=expectation_id,
        fields=declaration,
    )
    statement = DDLStatement(
        element_type="column_acl_expectation",
        element_id=expectation_id,
        source_path=PurePosixPath("epoch.sql"),
        sql="",
    )
    return product_provisioning._unapplication_sql(statement, element, (element,), ())


def test_fresh_epoch_unapplication_revokes_exact_column_privileges() -> None:
    """正式epoch権限を同じ列/ownerから取り外し、DROP/追加grantをしない。"""
    assert _fresh_epoch_unapplication(_fresh_epoch_acl()) == (
        'REVOKE SELECT ("recovery_generation"), UPDATE ("recovery_generation") '
        'ON TABLE "public"."rg1_restore_gate" FROM "pitchlog_rg1_control_owner";'
    )


@pytest.mark.parametrize(
    "field,value",
    (
        ("function_id", "FUNCTION:rg1_control:close_gate()"),
        ("grantee_role_id", "pitchlog_initial_actor"),
        ("object_id", "games"),
        ("column_id", "state"),
        ("privilege_ids", ["UPDATE"]),
        ("grant_option", 0),
    ),
)
def test_fresh_epoch_unapplication_rejects_unapproved_update(
    field: str, value: object
) -> None:
    """epochの撤去対応を無関係な更新権限へ流用しない。"""
    from pitchlog.authz.product_provisioning import ProductProvisioningError

    with pytest.raises(ProductProvisioningError):
        _fresh_epoch_unapplication({**_fresh_epoch_acl(), field: value})


def test_start_acl_and_policies_have_closed_real_tenant_predicates() -> None:
    """新列ACL/tenant両句は宣言全体に束縛し、旧生成器は保持する。"""
    from pitchlog.authz.initial_start_sql import (
        generate_start_policy_sql,
        is_start_column_acl,
        start_column_acl_declarations,
        start_policy_declarations,
        start_policy_expressions,
    )

    for key, row in start_column_acl_declarations().items():
        assert is_start_column_acl(row)
        assert key in generate_function_owner_column_acl_sql(row)
    for key, row in start_policy_declarations().items():
        using, check = start_policy_expressions(row)
        assert (using is not None) == (row["command"] in {"SELECT", "UPDATE"})
        assert (check is not None) == (row["command"] in {"INSERT", "UPDATE"})
        assert isinstance(using or check, str)
        assert "tenant_id" in str(using or check)
        roles = row["role_ids"]
        assert isinstance(roles, list)
        assert str(roles[0]) in generate_start_policy_sql(key)


@pytest.mark.parametrize(
    "field,value",
    [
        ("grantee_role_id", "pitchlog_app"),
        ("privilege_ids", ["DELETE"]),
        ("grant_option", True),
        ("grant_option", 0),
        ("column_id", "name"),
        ("object_id", "other"),
        ("object_schema", "other"),
        ("expectation_id", "unknown"),
        ("function_id", "unknown"),
    ],
)
def test_start_column_acl_mutations_never_use_generic_owner_exemption(
    field: str, value: object
) -> None:
    """新exact例外の全field改変は一般owner規則へ抜けない。"""
    from pitchlog.authz.initial_start_sql import (
        is_start_column_acl,
        start_column_acl_declarations,
    )

    row = next(iter(start_column_acl_declarations().values()))
    row[field] = value
    assert not is_start_column_acl(row)
    with pytest.raises((ValueError, KeyError)):
        generate_function_owner_column_acl_sql(row)


@pytest.mark.parametrize(
    "field,value",
    [
        ("role_ids", ["pitchlog_app"]),
        ("command", "DELETE"),
        ("using_expression", None),
        ("with_check_expression", None),
        ("using_column", "game_id"),
        ("profile", "shared"),
        ("policy_mode", "restrictive"),
        ("table_id", "games"),
    ],
)
def test_start_update_policy_mutations_rejected(field: str, value: object) -> None:
    """qual/checkの欠落も閉宣言比較でSQL/catalog期待に入れない。"""
    from pitchlog.authz.initial_start_sql import (
        start_policy_declarations,
        start_policy_expressions,
    )

    row = next(
        r for r in start_policy_declarations().values() if r["command"] == "UPDATE"
    )
    row[field] = value
    with pytest.raises(ValueError):
        start_policy_expressions(row)


@pytest.mark.parametrize(
    "mutation", ["renamed_joint", "initial_profile", "initial_owner", "initial_missing"]
)
def test_initial_table_universe_does_not_accept_count_only_joint_changes(
    mutation: str, tmp_path: Path
) -> None:
    """実50表は件数だけでなく旧45/RG1/初期exact4と全fieldを維持する。"""
    manifest = json.loads(
        (_REPOSITORY_ROOT / "contracts/db/schema-manifest.json").read_text()
    )
    classified = json.loads(
        (
            _REPOSITORY_ROOT / "contracts/authz/product/table-classification.json"
        ).read_text()
    )
    if mutation == "renamed_joint":
        next(row for row in manifest["tables"] if row["name"] == "players")["name"] = (
            "unknown_table"
        )
        next(row for row in classified["tables"] if row["table"] == "players")[
            "table"
        ] = "unknown_table"
    elif mutation == "initial_missing":
        manifest["tables"] = [
            r for r in manifest["tables"] if r["name"] != "trusted_devices"
        ]
        classified["tables"] = [
            r for r in classified["tables"] if r["table"] != "trusted_devices"
        ]
    else:
        row = next(
            row for row in classified["tables"] if row["table"] == "trusted_devices"
        )
        if mutation == "initial_profile":
            row["profile"] = "tenant_owned"
        else:
            row["access_path"]["owner_unit"] = "unknown"
    for relative, value in [
        ("contracts/db/schema-manifest.json", manifest),
        ("contracts/authz/product/table-classification.json", classified),
    ]:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value))
    with pytest.raises(_catalog_checker.CatalogError):
        _catalog_checker._product_table_universe(tmp_path)


@pytest.mark.parametrize(
    "mutation", ["unknown_actor", "role", "target", "qual", "check"]
)
def test_runtime_catalog_rejects_actor_policy_aliases_and_all_field_mutations(
    mutation: str,
) -> None:
    """sourcecheckerの代拒否に頼らずruntime期待生成前にactor閉集合を検査する。"""
    from pitchlog.authz import product_catalog
    from pitchlog.authz.initial_start_sql import start_policy_declarations

    asset = _product_asset()
    actor = next(
        row
        for row in start_policy_declarations().values()
        if row["role_ids"] == ["pitchlog_initial_actor"] and row["command"] == "UPDATE"
    )
    if mutation == "unknown_actor":
        actor = copy.deepcopy(actor)
        actor.update(
            policy_id="POLICY:players:unknown_actor_alias",
            policy_name="unknown_actor_alias",
            table_id="players",
            command="SELECT",
            using_expression="true",
            with_check_predicate_id=None,
            with_check_column=None,
            with_check_expression=None,
        )
        asset["policies"].append(actor)
    else:
        target = next(
            row for row in asset["policies"] if row["policy_id"] == actor["policy_id"]
        )
        if mutation == "role":
            target["role_ids"] = ["pitchlog_app"]
        elif mutation == "target":
            target["table_id"] = "games"
        elif mutation == "qual":
            target["using_expression"] = "true"
        elif mutation == "check":
            target["with_check_expression"] = None
    with pytest.raises(product_catalog.ProductCatalogError):
        product_catalog._validated_initial_policy_rows(asset)


@pytest.mark.parametrize(
    "roles",
    [["PUBLIC"], ["PUBLIC", "pitchlog_app"], ["public"], ["PuBlIc", "pitchlog_app"]],
)
def test_runtime_catalog_rejects_unknown_public_policy_effective_on_initial_roles(
    roles: list[str],
) -> None:
    """PUBLICの実効適用を明示actor/owner列挙の迂回口にしない。"""
    from pitchlog.authz import product_catalog
    from pitchlog.authz.initial_start_sql import start_policy_declarations

    asset = _product_asset()
    assert not any(
        any(role.upper() == "PUBLIC" for role in row["role_ids"])
        for row in asset["policies"]
    )
    unknown = next(
        row
        for row in start_policy_declarations().values()
        if row["table_id"] == "players"
        and row["command"] == "SELECT"
        and row["role_ids"] == ["pitchlog_initial_actor"]
    )
    unknown.update(
        policy_id="POLICY:players:unknown_public_alias",
        policy_name="unknown_public_alias",
        role_ids=roles,
        using_expression="true",
    )
    asset["policies"].append(unknown)
    with pytest.raises(product_catalog.ProductCatalogError):
        product_catalog._validated_initial_policy_rows(asset)


def _runtime_reserved_rows() -> list[tuple[str, str, str]]:
    """変更対象の全初期宣言を既source getterから採取する。"""
    from pitchlog.authz.initial_start_sql import (
        start_assets_present,
        start_column_acl_declarations,
        start_function_declarations,
        start_policy_declarations,
    )
    from pitchlog.authz.product_control_access import (
        build_initial_column_acl_declarations,
        build_initial_policy_declarations,
    )
    from pitchlog.authz.product_function_acl import build_initial_function_declarations
    from pitchlog.authz.product_table_access import build_product_policy_declaration

    functions = build_initial_function_declarations()
    columns = build_initial_column_acl_declarations()
    policies = build_initial_policy_declarations()
    if start_assets_present(_product_asset()):
        functions.update(start_function_declarations())
        columns.update(start_column_acl_declarations())
        policies.update(start_policy_declarations())
    for table in (
        "games",
        "team_records",
        "players",
        "game_lineups",
        "lineup_memories",
        "recording_generations",
    ):
        row = build_product_policy_declaration(table, "tenant_owned")
        key = row["policy_id"]
        assert isinstance(key, str)
        policies[key] = row
    return [
        (group, field, key)
        for group, field, rows in (
            ("functions", "function_id", functions),
            ("column_acl_expectations", "expectation_id", columns),
            ("policies", "policy_id", policies),
        )
        for key in rows
    ]


def _runtime_reserved_mutations() -> list[tuple[str, str, str, str]]:
    """全top field/ACL nested/削除重複unknownを漏れなく列挙する。"""
    asset = _product_asset()
    cases = []
    for group, identity, key in _runtime_reserved_rows():
        row = next(r for r in asset[group] if r[identity] == key)
        paths = ["@remove", "@duplicate", "@unknown", "@extra", *row]
        for field in ("acl_expectations", "revoked_acl_expectations"):
            for index, entry in enumerate(row.get(field, [])):
                paths.extend(f"{field}/{index}/{member}" for member in entry)
        cases.extend((group, identity, key, path) for path in paths)
    return cases


@pytest.mark.parametrize("group,identity,key,path", _runtime_reserved_mutations())
def test_runtime_entry_rejects_all_reserved_declaration_mutations(
    group: str, identity: str, key: str, path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sourcecheckerで代用せず実期待値生成入口が全限定変異を拒否する。"""
    from pitchlog.authz import product_catalog

    asset = _product_asset()
    row = next(r for r in asset[group] if r[identity] == key)
    if path == "@remove":
        asset[group].remove(row)
    elif path == "@duplicate":
        asset[group].append(copy.deepcopy(row))
    elif path == "@unknown":
        extra = copy.deepcopy(row)
        extra[identity] = key + ":runtime_unknown"
        asset[group].append(extra)
    elif path == "@extra":
        row["runtime_unknown"] = "extra"
    else:
        target = row
        parts = path.split("/")
        for part in parts[:-1]:
            target = target[int(part)] if isinstance(target, list) else target[part]
        member = parts[-1]
        old = target[member]
        target[member] = (
            0
            if type(old) is bool
            else ["runtime_mutated"]
            if old == []
            else []
            if isinstance(old, list)
            else "runtime_mutated"
        )
    monkeypatch.setattr(product_catalog, "_load_product_asset", lambda: asset)
    with pytest.raises(product_catalog.ProductCatalogError):
        product_catalog._load_product_expectations()


@pytest.mark.parametrize(
    "subject",
    ["pitchlog_initial_actor", "pitchlog_initial_fn_owner", "PUBLIC", "pitchlog_app"],
)
@pytest.mark.parametrize(
    "surface", ["table", "column", "function", "schema", "private_schema", "policy"]
)
def test_runtime_entry_rejects_unknown_effective_initial_subject_grants(
    subject: str, surface: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """actor/owner/PUBLICと保護app接点の未知権限を正規期待へ混入させない。"""
    from pitchlog.authz import product_catalog

    asset = _product_asset()
    if surface == "table":
        asset["acl_expectations"].append(
            dict(
                acl_id="ACL:players:runtime_unknown",
                object_kind="table",
                object_schema="public",
                object_id="players",
                grantee_role_id=subject,
                privilege_ids=["DELETE"],
                grant_option=False,
                profile="tenant_owned",
            )
        )
    elif surface == "column":
        table = "recording_generations" if subject == "pitchlog_app" else "players"
        asset["column_acl_expectations"].append(
            dict(
                expectation_id="COLUMN-ACL:runtime_unknown",
                object_kind="column",
                object_schema="public",
                object_id=table,
                column_id="uniform_number",
                grantee_role_id=subject,
                privilege_ids=["UPDATE"],
                grant_option=False,
            )
        )
    elif surface == "function":
        extra = copy.deepcopy(
            next(
                r
                for r in asset["functions"]
                if r.get("schema_name") == "initial_right_api"
            )
        )
        extra.update(
            function_id="FUNCTION:initial_right_api:runtime_unknown(uuid)",
            function_name="runtime_unknown",
            identity_args="uuid",
            acl_expectations=[
                dict(grantee=subject, privilege="EXECUTE", grantable=False)
            ],
        )
        asset["functions"].append(extra)
    elif surface == "schema":
        asset["schemas"].append(
            dict(
                schema_id="runtime_unknown",
                schema_name="runtime_unknown",
                creation="product_ddl",
                owner="pitchlog_owner",
                ownership_path="direct",
                acl_expectations=[
                    dict(grantee=subject, privilege="CREATE", grantable=False)
                ],
                revoked_acl_expectations=[],
            )
        )
    elif surface == "private_schema":
        next(r for r in asset["schemas"] if r["schema_id"] == "initial_right_api")[
            "acl_expectations"
        ].append(dict(grantee=subject, privilege="CREATE", grantable=False))
    else:
        from pitchlog.authz.product_table_access import build_product_policy_declaration

        extra = build_product_policy_declaration("players", "tenant_owned")
        extra.update(
            policy_id="POLICY:players:runtime_unknown",
            policy_name="runtime_unknown",
            role_ids=[subject],
            using_expression="true",
            with_check_expression="true",
        )
        asset["policies"].append(extra)
    monkeypatch.setattr(product_catalog, "_load_product_asset", lambda: asset)
    with pytest.raises(product_catalog.ProductCatalogError):
        product_catalog._load_product_expectations()


def test_runtime_entry_normal_profile_remains_accepted() -> None:
    """閉集合検査を通した正規期待値の全要素生成は維持する。"""
    from pitchlog.authz import product_catalog

    result = product_catalog._load_product_expectations()
    # 採用済data-model1.4/正式fullprofileの母集合を固定する。
    assert len(result.table_names) == 50 and len(result.role_ids) == 14
    assert len(result.schema_names) == 8
    assert len(result.functions) == 79 and len(result.policies) == 70
    assert len(_product_asset()["column_acl_expectations"]) == 123


@pytest.mark.parametrize(
    "table", ["games", "team_records", "players", "game_lineups", "lineup_memories"]
)
@pytest.mark.parametrize(
    "mode", ["remove", "duplicate", "unknown", "privilege", "grant_option", "extra"]
)
def test_runtime_entry_closes_touched_app_table_acls(
    table: str, mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """開始が触る正規app表権限を保持しつつ別名/DELETE等を拒否する。"""
    from pitchlog.authz import product_catalog

    asset = _product_asset()
    row = next(
        r
        for r in asset["acl_expectations"]
        if r.get("object_id") == table and r.get("grantee_role_id") == "pitchlog_app"
    )
    if mode == "remove":
        asset["acl_expectations"].remove(row)
    elif mode == "duplicate":
        asset["acl_expectations"].append(copy.deepcopy(row))
    elif mode == "unknown":
        extra = copy.deepcopy(row)
        extra["acl_id"] = "ACL:runtime_unknown"
        asset["acl_expectations"].append(extra)
    elif mode == "privilege":
        row["privilege_ids"] = ["DELETE"]
    elif mode == "grant_option":
        row["grant_option"] = 0
    else:
        row["unknown"] = "extra"
    monkeypatch.setattr(product_catalog, "_load_product_asset", lambda: asset)
    with pytest.raises(product_catalog.ProductCatalogError):
        product_catalog._load_product_expectations()


@pytest.mark.parametrize(
    "schema",
    [
        "public",
        "authz_private",
        "authn",
        "authn_crypto",
        "rg1_api",
        "rg1_control",
        "pitchlog_ledger_observer",
        "initial_right_api",
    ],
)
@pytest.mark.parametrize(
    "field",
    ["schema_id", "schema_name", "owner", "creation", "ownership_path", "extra"],
)
def test_runtime_entry_closes_initial_schema_contact_headers(
    schema: str, field: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """有限8schema接点のheaderをmutable metadataの自己根拠にしない。"""
    from pitchlog.authz import product_catalog

    asset = _product_asset()
    row = next(r for r in asset["schemas"] if r["schema_id"] == schema)
    row[field] = "runtime_unknown"
    monkeypatch.setattr(product_catalog, "_load_product_asset", lambda: asset)
    with pytest.raises(product_catalog.ProductCatalogError):
        product_catalog._load_product_expectations()


@pytest.mark.parametrize(
    "subject",
    ["pitchlog_initial_actor", "pitchlog_initial_fn_owner", "PUBLIC", "pitchlog_app"],
)
@pytest.mark.parametrize(
    "surface", ["schema_owner", "function_owner", "foreign_function_execute"]
)
def test_runtime_entry_closes_implicit_ownership_and_foreign_execute(
    subject: str, surface: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """所有による暗黙権限と別namespaceの初期subject実行権も閉じる。"""
    from pitchlog.authz import product_catalog

    asset = _product_asset()
    if surface == "schema_owner":
        asset["schemas"].append(
            dict(
                schema_id="runtime_unknown",
                schema_name="runtime_unknown",
                creation="product_ddl",
                owner=subject,
                ownership_path="direct",
                acl_expectations=[],
                revoked_acl_expectations=[],
            )
        )
    else:
        row = copy.deepcopy(
            next(
                r
                for r in asset["functions"]
                if r.get("schema_name") == "initial_right_api"
            )
        )
        row.update(
            function_id="FUNCTION:public:runtime_unknown(uuid)",
            schema_name="public",
            function_name="runtime_unknown",
            identity_args="uuid",
        )
        if surface == "function_owner":
            row["owner_role_id"] = subject
            row["acl_expectations"] = []
        else:
            # 一般app専用関数は範囲外。appの対向は初期owner接点を保つ。
            row["owner_role_id"] = (
                "pitchlog_initial_fn_owner"
                if subject == "pitchlog_app"
                else "pitchlog_owner"
            )
            row["acl_expectations"] = [
                dict(grantee=subject, privilege="EXECUTE", grantable=False)
            ]
        asset["functions"].append(row)
    monkeypatch.setattr(product_catalog, "_load_product_asset", lambda: asset)
    with pytest.raises(product_catalog.ProductCatalogError):
        product_catalog._load_product_expectations()


@pytest.mark.parametrize(
    "function_id",
    [
        "FUNCTION:rg1_api:rg1_read_open(uuid)",
        "FUNCTION:rg1_api:rg1_assert_open_before_commit(uuid)",
        "FUNCTION:rg1_control:scope_binding(uuid)",
    ],
)
@pytest.mark.parametrize(
    "subject",
    ["pitchlog_initial_actor", "pitchlog_initial_fn_owner", "PUBLIC", "pitchlog_app"],
)
def test_runtime_entry_rejects_foreign_initial_contact_owner_change(
    function_id: str, subject: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """既actor接点を別subject所有へ変える経路も許可しない。"""
    from pitchlog.authz import product_catalog

    asset = _product_asset()
    row = next(r for r in asset["functions"] if r["function_id"] == function_id)
    row["owner_role_id"] = subject
    monkeypatch.setattr(product_catalog, "_load_product_asset", lambda: asset)
    with pytest.raises(product_catalog.ProductCatalogError):
        product_catalog._load_product_expectations()


def _runtime_schema_acl_mutations() -> list[tuple[str, str, int, str]]:
    """有限schemaの保護ACLリーフと行の欠落/重複を列挙する。"""
    cases = []
    subjects = {
        "PUBLIC",
        "pitchlog_app",
        "pitchlog_initial_actor",
        "pitchlog_initial_fn_owner",
    }
    for row in _product_asset()["schemas"]:
        for group in ("acl_expectations", "revoked_acl_expectations"):
            for index, entry in enumerate(row[group]):
                if entry["grantee"] in subjects:
                    cases.extend(
                        (row["schema_id"], group, index, field)
                        for field in ("@remove", "@duplicate", "@extra", *entry)
                    )
    return cases


@pytest.mark.parametrize("schema,group,index,field", _runtime_schema_acl_mutations())
def test_runtime_entry_closes_all_initial_schema_acl_fields(
    schema: str, group: str, index: int, field: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ACLの型/主体/権限/未知keyも期待生成前に全field照合する。"""
    from pitchlog.authz import product_catalog

    asset = _product_asset()
    entries = next(r for r in asset["schemas"] if r["schema_id"] == schema)[group]
    entry = entries[index]
    if field == "@remove":
        entries.pop(index)
    elif field == "@duplicate":
        entries.append(copy.deepcopy(entry))
    elif field == "@extra":
        entry["runtime_unknown"] = True
    else:
        entry[field] = 0 if type(entry[field]) is bool else "runtime_unknown"
    monkeypatch.setattr(product_catalog, "_load_product_asset", lambda: asset)
    with pytest.raises(product_catalog.ProductCatalogError):
        product_catalog._load_product_expectations()


def _b2_enrollment_asset() -> dict[str, Any]:
    """既全宣言に新関数/policy/3列overlayだけを追加する試験入力。"""
    from pitchlog.authz.product_control_access import (
        build_enrollment_column_acl_declarations,
        build_enrollment_policy_declarations,
    )
    from pitchlog.authz.product_function_acl import (
        build_enrollment_function_declarations,
    )

    asset = _product_asset()
    for section, key, additions in [
        ("functions", "function_id", build_enrollment_function_declarations()),
        ("policies", "policy_id", build_enrollment_policy_declarations()),
        (
            "column_acl_expectations",
            "expectation_id",
            build_enrollment_column_acl_declarations(),
        ),
    ]:
        asset[section] = [row for row in asset[section] if row[key] not in additions]
        asset[section].extend(additions.values())
    return asset


def test_b2_enrollment_exact_overlay_and_single_tenant_policy() -> None:
    """旧53行を変えず3列INSERTだけを増やし、TENANT実式を再利用する。"""
    from pitchlog.authz.product_control_access import (
        build_enrollment_column_acl_declarations,
        build_enrollment_policy_declarations,
        build_initial_column_acl_declarations,
        enrollment_policy_expressions,
        generate_enrollment_policy_sql,
    )

    old = build_initial_column_acl_declarations()
    overlay = build_enrollment_column_acl_declarations()
    assert len(old) == 53 and len(overlay) == 3
    for key, row in overlay.items():
        privileges = old[key]["privilege_ids"]
        assert isinstance(privileges, list)
        assert row == {
            **old[key],
            "privilege_ids": privileges + ["INSERT"],
        }
        assert "INSERT" not in privileges
        assert f"INSERT ({row['column_id']})" in (
            generate_function_owner_column_acl_sql(row)
        )
    policy = next(iter(build_enrollment_policy_declarations().values()))
    using, check = enrollment_policy_expressions(policy)
    assert using is None and isinstance(check, str) and "app.tenant_id" in check
    assert check in generate_enrollment_policy_sql()


@pytest.mark.parametrize(
    "surface", ["functions", "policies", "column_acl_expectations"]
)
@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "unknown", "owner", "privilege", "extra"]
)
def test_b2_runtime_entry_rejects_partial_or_mutated_enrollment(
    surface: str,
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """新1/1/overlay3の部分欠落と未知fieldを期待生成前に拒否する。"""
    from pitchlog.authz import product_catalog
    from pitchlog.authz.product_control_access import ENROLL_POLICY_ID
    from pitchlog.authz.product_function_acl import ENROLL_FUNCTION_ID

    asset = _b2_enrollment_asset()
    key = {
        "functions": "function_id",
        "policies": "policy_id",
        "column_acl_expectations": "expectation_id",
    }[surface]
    target = {
        "functions": ENROLL_FUNCTION_ID,
        "policies": ENROLL_POLICY_ID,
        "column_acl_expectations": (
            "COLUMN-ACL:public:trusted_devices:tenant_id:pitchlog_initial_fn_owner"
        ),
    }[surface]
    row = next(r for r in asset[surface] if r[key] == target)
    if mutation == "missing":
        asset[surface].remove(row)
    elif mutation == "duplicate":
        asset[surface].append(copy.deepcopy(row))
    elif mutation == "unknown":
        row[key] += ":unknown"
    elif mutation == "owner":
        row[
            "owner_role_id"
            if surface == "functions"
            else "role_ids"
            if surface == "policies"
            else "grantee_role_id"
        ] = "pitchlog_app"
    elif mutation == "privilege":
        row[
            "security_mode"
            if surface == "functions"
            else "with_check_expression"
            if surface == "policies"
            else "privilege_ids"
        ] = "unknown"
    else:
        row["unknown_field"] = True
    monkeypatch.setattr(product_catalog, "_load_product_asset", lambda: asset)
    with pytest.raises(product_catalog.ProductCatalogError):
        product_catalog._load_product_expectations()


@pytest.mark.parametrize(
    "group,identity,key",
    [
        ("functions", "function_id", "FUNCTION:public:protect_initial_right_storage()"),
        ("schemas", "schema_id", "public"),
        ("databases", "database_id", "current_database"),
    ],
)
@pytest.mark.parametrize("field", ["acl_expectations", "revoked_acl_expectations"])
@pytest.mark.parametrize("value", [None, {}, "invalid", ["invalid"], [None], [0]])
def test_runtime_verifier_nested_acl_rejects_non_object_arrays(
    group: str,
    identity: str,
    key: str,
    field: str,
    value: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全nested ACLは非list/非dictをtyped拒否し、属性例外へ漏らさない。"""
    from pitchlog.authz import product_catalog

    asset = _product_asset()
    row = next(r for r in asset[group] if r[identity] == key)
    row[field] = copy.deepcopy(value)
    monkeypatch.setattr(product_catalog, "_load_product_asset", lambda: asset)
    with pytest.raises(product_catalog.ProductCatalogError, match="metadata配列の形"):
        product_catalog._load_product_expectations()
