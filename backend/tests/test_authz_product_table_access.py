"""製品表の直接アクセスポリシーとACLを検査する。"""

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
from pitchlog.authz.product_table_access import (
    TENANT_PREDICATE_ID,
    TENANT_PREDICATE_TEMPLATE,
    generate_product_policy_sql,
    generate_product_predicate_sql,
    generate_product_table_acl_sql,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_CHECKER = _REPOSITORY_ROOT / "scripts/check_authz_catalog.py"
_TABLE_CLASSIFICATION = (
    _REPOSITORY_ROOT / "contracts/authz/product/table-classification.json"
)
_EXPOSURE_FACTS = _REPOSITORY_ROOT / "contracts/authz/product/exposure-facts.json"
_PROFILE_RULES = {
    "tenant_owned": {
        "command": "ALL",
        "column": "tenant_id",
        "with_check": True,
        "privileges": ("SELECT", "INSERT", "UPDATE"),
    },
    "self_tenant_row": {
        "command": "SELECT",
        "column": "id",
        "with_check": False,
        "privileges": ("SELECT",),
    },
    "global_read_only": {
        "command": "SELECT",
        "column": None,
        "with_check": False,
        "privileges": ("SELECT",),
    },
}


def _load_catalog_checker() -> Any:
    """静的検査を独立したモジュール名で読み込む。"""
    module_spec = importlib.util.spec_from_file_location(
        "check_authz_catalog_product_table_access_under_test",
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


def _table_profiles() -> dict[str, str]:
    """表分類から表とプロファイルの写像を読む。"""
    rows = _read_json_object(_TABLE_CLASSIFICATION)["tables"]
    assert isinstance(rows, list)
    return {str(row["table"]): str(row["profile"]) for row in rows}


def _secret_columns() -> set[tuple[str, str]]:
    """露出の事実から秘密列を読む。"""
    facts = _read_json_object(_EXPOSURE_FACTS)["facts"]
    assert isinstance(facts, list)
    entries = next(fact["entries"] for fact in facts if fact["kind"] == "secret_column")
    return {(str(entry["table"]), str(entry["column"])) for entry in entries}


def _validate_product_asset(
    asset: dict[str, Any],
    root: Path = _REPOSITORY_ROOT,
) -> dict[str, object]:
    """製品DDL資産を静的検査へ渡す。"""
    return _catalog_checker.validate_ddl_elements(asset, root, PRODUCT_SPEC)


def _copy_static_inputs(root: Path) -> None:
    """生成body検査に必要な資産を一時領域へ複製する。"""
    paths = (
        Path("contracts/db/schema-manifest.json"),
        Path("contracts/authz/product/table-classification.json"),
        Path("contracts/authz/product/exposure-facts.json"),
        PRODUCT_SPEC.ddl_elements_path,
        PRODUCT_SPEC.body_manifest_path,
    )
    for relative_path in paths:
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_REPOSITORY_ROOT / relative_path, destination)
    shutil.copytree(
        _REPOSITORY_ROOT / PRODUCT_SPEC.body_directory,
        root / PRODUCT_SPEC.body_directory,
        dirs_exist_ok=True,
    )


def _rows_by_table(asset: dict[str, Any], section: str) -> dict[str, dict[str, Any]]:
    """ポリシーまたはACL宣言を対象表で引ける形へ変換する。"""
    field = "table_id" if section == "policies" else "object_id"
    rows = asset[section]
    assert isinstance(rows, list)
    result = {str(row[field]): row for row in rows}
    assert len(result) == len(rows)
    return result


def _append_table_acl(
    asset: dict[str, Any],
    table_id: str,
    profile: str,
    privileges: list[str],
) -> None:
    """変異用のpitchlog_app表ACLを追加する。"""
    asset["acl_expectations"].append(
        {
            "acl_id": f"ACL:{table_id}:pitchlog_app",
            "object_kind": "table",
            "object_schema": "public",
            "object_id": table_id,
            "profile": profile,
            "grantee_role_id": "pitchlog_app",
            "privilege_ids": privileges,
            "grant_option": False,
        }
    )


def _mutate_remove_policy(asset: dict[str, Any]) -> None:
    """ポリシーを1本消す。"""
    asset["policies"].pop()


def _mutate_remove_with_check(asset: dict[str, Any]) -> None:
    """tenant_ownedポリシーからWITH CHECK宣言を消す。"""
    policy = next(row for row in asset["policies"] if row["profile"] == "tenant_owned")
    del policy["with_check_expression"]


def _mutate_add_delete(asset: dict[str, Any]) -> None:
    """tenant_owned表ACLへDELETEを足す。"""
    acl = next(
        row for row in asset["acl_expectations"] if row["profile"] == "tenant_owned"
    )
    acl["privilege_ids"].append("DELETE")


def _mutate_function_only_acl(asset: dict[str, Any]) -> None:
    """function_only表へSELECTを足す。"""
    _append_table_acl(asset, "migration_runs", "function_only", ["SELECT"])


def _mutate_predicate_uuid_type(asset: dict[str, Any]) -> None:
    """TENANT述語のUUIDキャストをBIGINTへ変える。"""
    predicate = asset["predicates"][0]
    predicate["expression_template"] = predicate["expression_template"].replace(
        "::UUID",
        "::BIGINT",
    )


def _mutate_control_resource_acl(asset: dict[str, Any]) -> None:
    """制御資源へpitchlog_appのSELECTを足す。"""
    _append_table_acl(
        asset,
        "analysis_groups",
        "effective_group_control",
        ["SELECT"],
    )


def _mutate_secret_column_acl(asset: dict[str, Any]) -> None:
    """秘密列へpitchlog_appの列単位SELECTを足す。"""
    asset["column_acl_expectations"].append(
        {
            "expectation_id": (
                "COLUMN-ACL:tenant_credentials:password_hash:pitchlog_app"
            ),
            "object_kind": "table",
            "object_schema": "public",
            "object_id": "tenant_credentials",
            "column_id": "password_hash",
            "grantee_role_id": "pitchlog_app",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        }
    )


def _mutate_secret_table_acl(asset: dict[str, Any]) -> None:
    """秘密列を持つ表へpitchlog_appの表単位SELECTを足す。"""
    _append_table_acl(
        asset,
        "tenant_credentials",
        "function_only",
        ["SELECT"],
    )


def test_product_policies_and_table_acls_match_three_direct_profiles() -> None:
    """3プロファイルのポリシー・ACL・展開SQLが設計へ一致する。"""
    asset = _product_asset()
    _validate_product_asset(asset)
    profiles = _table_profiles()
    policies = _rows_by_table(asset, "policies")
    table_acls = _rows_by_table(asset, "acl_expectations")
    direct_tables = {
        table_id for table_id, profile in profiles.items() if profile in _PROFILE_RULES
    }
    assert len(direct_tables) == 28
    assert set(policies) == set(table_acls) == direct_tables

    predicates = asset["predicates"]
    assert predicates == [
        {
            "predicate_id": TENANT_PREDICATE_ID,
            "predicate_kind": "tenant_column",
            "parameter": "column",
            "expression_template": (
                "COALESCE({column} = NULLIF("
                "pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE)"
            ),
        }
    ]
    assert predicates[0]["expression_template"] == TENANT_PREDICATE_TEMPLATE

    for table_id, profile in profiles.items():
        if profile not in _PROFILE_RULES:
            assert table_id not in policies
            assert table_id not in table_acls
            continue
        rule = _PROFILE_RULES[profile]
        policy = policies[table_id]
        acl = table_acls[table_id]
        assert policy["command"] == rule["command"]
        assert policy["role_ids"] == ["pitchlog_app"]
        assert policy["using_column"] == rule["column"]
        assert (policy["with_check_expression"] is not None) is rule["with_check"]
        assert tuple(acl["privilege_ids"]) == rule["privileges"]
        assert acl["grantee_role_id"] == "pitchlog_app"
        assert "DELETE" not in acl["privilege_ids"]
        assert "TRUNCATE" not in acl["privilege_ids"]
        assert "REFERENCES" not in acl["privilege_ids"]
        assert "TRIGGER" not in acl["privilege_ids"]

    secret_columns = _secret_columns()
    secret_tables = {table_id for table_id, _ in secret_columns}
    assert secret_tables.isdisjoint(table_acls)
    assert asset["column_acl_expectations"] == []

    statements = generate_authz_ddl(_REPOSITORY_ROOT, PRODUCT_SPEC)
    actual_sql = {
        (statement.element_type, statement.element_id): statement.sql
        for statement in statements
        if statement.element_type in {"predicate", "policy", "acl_expectation"}
    }
    expected_sql = {
        ("predicate", TENANT_PREDICATE_ID): generate_product_predicate_sql()
    }
    for table_id in direct_tables:
        profile = profiles[table_id]
        expected_sql[("policy", f"POLICY:{table_id}:{profile}")] = (
            generate_product_policy_sql(table_id, profile)
        )
        expected_sql[("acl_expectation", f"ACL:{table_id}:pitchlog_app")] = (
            generate_product_table_acl_sql(table_id, profile)
        )
    assert actual_sql == expected_sql


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_mutate_remove_policy, id="policy-removed"),
        pytest.param(_mutate_remove_with_check, id="with-check-removed"),
        pytest.param(_mutate_add_delete, id="delete-added"),
        pytest.param(_mutate_function_only_acl, id="function-only-acl"),
        pytest.param(_mutate_predicate_uuid_type, id="uuid-to-bigint"),
        pytest.param(_mutate_control_resource_acl, id="control-resource-acl"),
        pytest.param(_mutate_secret_table_acl, id="secret-table-select"),
        pytest.param(_mutate_secret_column_acl, id="secret-column-select"),
    ],
)
def test_product_table_access_declaration_mutations_are_rejected(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    """正常資産を確認後、ポリシーとACLの各変異を拒否する。"""
    asset = _product_asset()
    _validate_product_asset(asset)
    mutated = copy.deepcopy(asset)
    mutate(mutated)

    with pytest.raises(_catalog_checker.CatalogError):
        _validate_product_asset(mutated)


def test_hand_edited_expanded_policy_body_is_rejected(tmp_path: Path) -> None:
    """正常bodyを確認後、手書きで変えた述語展開結果を拒否する。"""
    root = tmp_path / "repository"
    _copy_static_inputs(root)
    asset = _product_asset()
    _validate_product_asset(asset, root)

    profile = "tenant_owned"
    policy_id = f"POLICY:team_records:{profile}"
    body_path = root / PRODUCT_SPEC.body_directory / "policies" / f"{policy_id}.sql"
    text = body_path.read_text(encoding="utf-8")
    assert text.count("::UUID, FALSE)") == 2
    body_path.write_text(text.replace("::UUID, FALSE)", "::UUID, TRUE", 1))

    with pytest.raises(_catalog_checker.CatalogError, match="生成器と不一致"):
        _validate_product_asset(asset, root)
