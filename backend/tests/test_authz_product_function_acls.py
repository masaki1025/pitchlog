"""製品DDLのmigrationトリガ関数ACLを検査する。"""

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
from pitchlog.authz.product_function_acl import (
    build_product_function_acl_declaration,
    generate_product_function_acl_sql,
    product_function_id,
)
from pitchlog.authz.runtime_contract import PROTECTED_FUNCTIONS

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_CHECKER = _REPOSITORY_ROOT / "scripts/check_authz_catalog.py"
_MIGRATION_VERSIONS = Path("backend/migrations/versions")
_EXPECTED_GAPS = {
    (
        "public",
        "prevent_invalidation_intents_target_update",
        "",
    ): "0015_invalidation_intents",
    (
        "public",
        "prevent_migration_quarantine_mutation",
        "",
    ): "0016_migration_quarantine",
    (
        "public",
        "prevent_migrated_final_lineups_source_update",
        "",
    ): "0017_migrated_final_lineups",
    (
        "public",
        "prevent_players_identity_update",
        "",
    ): "0024_players_identity_trigger",
}


def _load_catalog_checker() -> Any:
    """静的検査を独立したモジュール名で読み込む。"""
    module_spec = importlib.util.spec_from_file_location(
        "check_authz_catalog_product_function_acls_under_test",
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
    """関数ACL検査に必要な資産とmigrationを一時領域へ複製する。"""
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
    shutil.copytree(
        _REPOSITORY_ROOT / _MIGRATION_VERSIONS,
        root / _MIGRATION_VERSIONS,
    )


def _function_rows(asset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """関数宣言を関数IDで引ける形へ変換する。"""
    rows = asset["functions"]
    assert isinstance(rows, list)
    result = {str(row["function_id"]): row for row in rows}
    assert len(result) == len(rows)
    return result


def _mutate_add_unknown_function(asset: dict[str, Any]) -> None:
    """Migration母集合にない関数を宣言へ足す。"""
    asset["functions"].append(
        build_product_function_acl_declaration(
            "public",
            "not_created_by_migration",
            "",
        )
    )


def _mutate_remove_function(asset: dict[str, Any]) -> None:
    """Migration関数の宣言を1件消す。"""
    index = next(
        index
        for index, row in enumerate(asset["functions"])
        if row["function_kind"] == "migration_trigger"
    )
    asset["functions"].pop(index)


def _mutate_remove_gap(asset: dict[str, Any]) -> None:
    """暫定契約の宣言済み追加分を1件消す。"""
    index = next(
        index
        for index, row in enumerate(asset["provisional_contract_additions"])
        if row["reason"] == "provisional_contract_gap"
    )
    asset["provisional_contract_additions"].pop(index)


def _mutate_add_reasonless_gap(asset: dict[str, Any]) -> None:
    """理由を持たない関数を暫定契約の追加分へ足す。"""
    schema_name, function_name, identity_args = PROTECTED_FUNCTIONS[0]
    asset["provisional_contract_additions"].append(
        {
            "addition_id": product_function_id(
                schema_name,
                function_name,
                identity_args,
            ),
            "object_kind": "function",
            "schema_name": schema_name,
            "object_name": function_name,
            "identity_args": identity_args,
            "detail": "理由コードがない不正な追加分",
            "migration_revision": "0000_unknown",
        }
    )


def test_migration_function_acls_and_provisional_gaps_match_exactly() -> None:
    """Migration 37関数と暫定契約との差4件が宣言へ完全一致する。"""
    asset = _product_asset()
    _validate_product_asset(asset)

    migration_origins = _catalog_checker._product_migration_functions(_REPOSITORY_ROOT)
    migration_functions = set(migration_origins)
    provisional_functions = {
        (str(schema), str(name), str(identity_args))
        for schema, name, identity_args in PROTECTED_FUNCTIONS
    }
    assert len(migration_functions) == 37
    assert len(provisional_functions) == 33
    assert migration_functions - provisional_functions == set(_EXPECTED_GAPS)
    assert provisional_functions <= migration_functions
    for physical_id, revision in _EXPECTED_GAPS.items():
        assert revision in migration_origins[physical_id]

    functions = {
        function_id: row
        for function_id, row in _function_rows(asset).items()
        if row["function_kind"] == "migration_trigger"
    }
    expected_ids = {
        product_function_id(schema_name, function_name, identity_args)
        for schema_name, function_name, identity_args in migration_functions
    }
    assert set(functions) == expected_ids
    for function_id, row in functions.items():
        assert row["owner_role_id"] == "pitchlog_owner"
        assert row["acl_expectations"] == []
        assert row["revoked_acl_expectations"] == [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
            {
                "grantee": "pitchlog_app",
                "privilege": "EXECUTE",
                "grantable": False,
            },
        ]
        assert function_id == product_function_id(
            str(row["schema_name"]),
            str(row["function_name"]),
            str(row["identity_args"]),
        )

    additions = [
        row
        for row in asset["provisional_contract_additions"]
        if row["reason"] == "provisional_contract_gap"
    ]
    assert isinstance(additions, list) and len(additions) == 4
    assert {
        (
            str(row["schema_name"]),
            str(row["object_name"]),
            str(row["identity_args"]),
        ): str(row["migration_revision"])
        for row in additions
    } == _EXPECTED_GAPS
    assert all(row["reason"] == "provisional_contract_gap" for row in additions)

    statements = generate_authz_ddl(_REPOSITORY_ROOT, PRODUCT_SPEC)
    function_sql = {
        statement.element_id: statement.sql
        for statement in statements
        if statement.element_type == "function" and statement.element_id in expected_ids
    }
    assert set(function_sql) == expected_ids
    for row in functions.values():
        function_id = str(row["function_id"])
        assert function_sql[function_id] == generate_product_function_acl_sql(
            str(row["schema_name"]),
            str(row["function_name"]),
            str(row["identity_args"]),
        )


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_mutate_add_unknown_function, id="unknown-function"),
        pytest.param(_mutate_remove_function, id="function-removed"),
        pytest.param(_mutate_remove_gap, id="gap-removed"),
        pytest.param(_mutate_add_reasonless_gap, id="reasonless-gap"),
    ],
)
def test_function_acl_declaration_mutations_are_rejected(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    """正常資産を確認後、関数または追加分の宣言変異を拒否する。"""
    asset = _product_asset()
    _validate_product_asset(asset)
    mutated = copy.deepcopy(asset)
    mutate(mutated)

    with pytest.raises(_catalog_checker.CatalogError):
        _validate_product_asset(mutated)


def test_removing_one_public_execute_revocation_is_rejected(tmp_path: Path) -> None:
    """正常bodyを確認後、PUBLIC EXECUTE剥奪の欠落を拒否する。"""
    root = tmp_path / "repository"
    _copy_static_inputs(root)
    asset = _product_asset()
    _validate_product_asset(asset, root)

    physical_id = sorted(_catalog_checker._product_migration_functions(root))[0]
    schema_name, function_name, identity_args = physical_id
    function_id = product_function_id(schema_name, function_name, identity_args)
    body_path = root / PRODUCT_SPEC.body_directory / "functions" / f"{function_id}.sql"
    text = body_path.read_text(encoding="utf-8")
    target = (
        f"REVOKE EXECUTE ON FUNCTION {schema_name}.{function_name}({identity_args}) "
        "FROM PUBLIC;\n"
    )
    assert text.count(target) == 1
    body_path.write_text(text.replace(target, "", 1), encoding="utf-8")

    with pytest.raises(_catalog_checker.CatalogError, match="剥奪が生成結果と不一致"):
        _validate_product_asset(asset, root)
