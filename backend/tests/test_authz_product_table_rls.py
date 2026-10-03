"""製品認可DDLの全表RLS有効化とFORCEを検査する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from pitchlog.authz.asset_spec import PRODUCT_SPEC
from pitchlog.authz.ddl import generate_authz_ddl
from pitchlog.authz.product_table_rls import generate_product_table_rls_sql

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_CHECKER = _REPOSITORY_ROOT / "scripts/check_authz_catalog.py"
_SCHEMA_MANIFEST = _REPOSITORY_ROOT / "contracts/db/schema-manifest.json"
_TABLE_CLASSIFICATION = (
    _REPOSITORY_ROOT / "contracts/authz/product/table-classification.json"
)


def _load_catalog_checker() -> Any:
    """静的検査を独立したモジュール名で読み込む。"""
    module_spec = importlib.util.spec_from_file_location(
        "check_authz_catalog_product_table_rls_under_test",
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


def _manifest_table_names() -> set[str]:
    """Schema manifestから表名の母集合を導く。"""
    manifest = _read_json_object(_SCHEMA_MANIFEST)
    rows = manifest["tables"]
    assert isinstance(rows, list)
    return {str(row["name"]) for row in rows}


def _classified_table_names() -> set[str]:
    """表分類資産から表名の母集合を導く。"""
    classification = _read_json_object(_TABLE_CLASSIFICATION)
    rows = classification["tables"]
    assert isinstance(rows, list)
    return {str(row["table"]) for row in rows}


def _validate_product_asset(
    asset: dict[str, Any],
    root: Path = _REPOSITORY_ROOT,
) -> dict[str, object]:
    """製品DDL資産を静的検査へ渡す。"""
    return _catalog_checker.validate_ddl_elements(asset, root, PRODUCT_SPEC)


def _copy_static_table_inputs(root: Path) -> None:
    """表の静的検査が読む正本・manifest・bodyを一時領域へ複製する。"""
    paths = (
        Path("contracts/db/schema-manifest.json"),
        Path("contracts/authz/product/table-classification.json"),
        PRODUCT_SPEC.body_manifest_path,
    )
    for relative_path in paths:
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_REPOSITORY_ROOT / relative_path, destination)
    source_directory = _REPOSITORY_ROOT / PRODUCT_SPEC.body_directory / "tables"
    destination_directory = root / PRODUCT_SPEC.body_directory / "tables"
    shutil.copytree(source_directory, destination_directory)


def test_all_manifest_and_classified_tables_have_generated_enable_and_force() -> None:
    """両母集合の全45表が生成済みENABLE・FORCE SQLと一致する。"""
    manifest_tables = _manifest_table_names()
    classified_tables = _classified_table_names()
    assert len(manifest_tables) == len(classified_tables) == 45
    assert manifest_tables == classified_tables

    asset = _product_asset()
    _validate_product_asset(asset)
    rows = asset["tables"]
    assert isinstance(rows, list)
    declared_tables = {str(row["table_id"]) for row in rows}
    assert declared_tables == manifest_tables
    assert all(
        row
        == {
            "table_id": row["table_id"],
            "schema_name": "public",
            "enable_row_level_security": True,
            "force_row_level_security": True,
        }
        for row in rows
    )

    generated = generate_authz_ddl(_REPOSITORY_ROOT, PRODUCT_SPEC)
    table_statements = {
        statement.element_id: statement.sql
        for statement in generated
        if statement.element_type == "table"
    }
    assert set(table_statements) == manifest_tables
    assert table_statements == {
        table_id: generate_product_table_rls_sql(table_id)
        for table_id in manifest_tables
    }


@pytest.mark.parametrize(
    "clause",
    [
        pytest.param("ENABLE ROW LEVEL SECURITY", id="enable-removed"),
        pytest.param("FORCE ROW LEVEL SECURITY", id="force-removed"),
    ],
)
def test_removing_enable_or_force_from_one_body_is_rejected(
    tmp_path: Path,
    clause: str,
) -> None:
    """正常な全bodyを確認後、1表のENABLEまたはFORCE欠落を拒否する。"""
    root = tmp_path / "repository"
    _copy_static_table_inputs(root)
    asset = _product_asset()
    _validate_product_asset(asset, root)

    table_id = sorted(_manifest_table_names())[0]
    body_path = root / PRODUCT_SPEC.body_directory / "tables" / f"{table_id}.sql"
    text = body_path.read_text(encoding="utf-8")
    target = f"    {clause};\n"
    assert text.count(target) == 1
    body_path.write_text(text.replace(target, "", 1), encoding="utf-8")

    with pytest.raises(_catalog_checker.CatalogError, match="生成結果と不一致"):
        _validate_product_asset(asset, root)


def test_removing_one_declared_table_is_rejected() -> None:
    """正常宣言を確認後、1表の宣言欠落をexact-setで拒否する。"""
    asset = _product_asset()
    _validate_product_asset(asset)
    mutated = copy.deepcopy(asset)
    rows = mutated["tables"]
    assert isinstance(rows, list) and len(rows) == 45
    rows.pop()

    with pytest.raises(_catalog_checker.CatalogError, match="exact-set不一致"):
        _validate_product_asset(mutated)


def test_adding_unknown_declared_table_is_rejected() -> None:
    """正常宣言を確認後、母集合に無い表の追加をexact-setで拒否する。"""
    asset = _product_asset()
    _validate_product_asset(asset)
    mutated = copy.deepcopy(asset)
    rows = mutated["tables"]
    assert isinstance(rows, list)
    rows.append(
        {
            "table_id": "not_in_schema_manifest",
            "schema_name": "public",
            "enable_row_level_security": True,
            "force_row_level_security": True,
        }
    )

    with pytest.raises(_catalog_checker.CatalogError, match="exact-set不一致"):
        _validate_product_asset(mutated)


@pytest.mark.parametrize(
    "table_id",
    ["PublicTable", "quoted-table", "public.table", ""],
)
def test_table_sql_generator_rejects_noncanonical_identifiers(table_id: str) -> None:
    """SQL生成器は引用や修飾が必要な識別子を拒否する。"""
    with pytest.raises(ValueError, match="表識別子が不正"):
        generate_product_table_rls_sql(table_id)
