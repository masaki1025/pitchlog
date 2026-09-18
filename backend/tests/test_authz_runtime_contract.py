"""ランタイム認可契約の生成一致と二状態切替を検査する。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from pitchlog.authz import runtime_contract

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_PROVISIONAL_ASSET = Path("contracts/tenant_boundary/runtime-authz-contract.json")
_PRODUCT_ASSET = Path("contracts/authz/product/ddl-elements.json")
_SCHEMA_MANIFEST = Path("contracts/db/schema-manifest.json")
_DANGEROUS_ENDPOINT_CATEGORIES = {
    "superuser",
    "bypassrls",
    "schema_owner",
    "table_owner",
    "function_owner",
}
_ROLE_ATTRIBUTE_NAMES = {
    "rolsuper",
    "rolbypassrls",
    "rolcanlogin",
    "rolcreaterole",
    "rolcreatedb",
    "rolreplication",
    "rolinherit",
}


def _read_json_object(path: Path) -> dict[str, Any]:
    """JSON object を読み込む。

    Args:
        path: 読み込む資産の絶対パス。

    Returns:
        文字列キーを持つ JSON object。
    """
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise AssertionError(f"JSON object ではない: {path}")
    return value


def _asset_digest(asset: dict[str, Any]) -> str:
    """資産自身の digest 欄を除いて正規化 digest を計算する。"""
    payload = dict(asset)
    payload.pop("source_digest", None)
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _active_asset_contract() -> tuple[Path, dict[str, Any]]:
    """製品資産の有無から有効なランタイム契約を選ぶ。

    Returns:
        有効資産の相対パスとランタイム契約 object。
    """
    product_path = _REPOSITORY_ROOT / _PRODUCT_ASSET
    if not product_path.exists():
        return (
            _PROVISIONAL_ASSET,
            _read_json_object(_REPOSITORY_ROOT / _PROVISIONAL_ASSET),
        )

    product_asset = _read_json_object(product_path)
    contract = product_asset.get("runtime_contract")
    if not isinstance(contract, dict) or not all(
        isinstance(key, str) for key in contract
    ):
        raise AssertionError("製品資産に runtime_contract object がない")
    return _PRODUCT_ASSET, contract


def _generated_snapshot() -> dict[str, object]:
    """生成モジュールの公開契約を JSON と比較できる形へ変換する。"""
    return {
        "schema_version": runtime_contract.SCHEMA_VERSION,
        "provisional": runtime_contract.PROVISIONAL,
        "superseded_by": runtime_contract.SUPERSEDED_BY,
        "source_digest": runtime_contract.SOURCE_DIGEST,
        "application_role": {
            "rolname": runtime_contract.APPLICATION_ROLE_NAME,
            "attributes": asdict(runtime_contract.APPLICATION_ROLE_ATTRIBUTES),
        },
        "protected_objects": {
            "schemas": list(runtime_contract.PROTECTED_SCHEMAS),
            "tables": [list(value) for value in runtime_contract.PROTECTED_TABLES],
            "functions": [
                list(value) for value in runtime_contract.PROTECTED_FUNCTIONS
            ],
        },
        "dangerous_endpoint_fixtures": [
            {"category": category, "fixture_id": fixture_id}
            for category, fixture_id in runtime_contract.DANGEROUS_ENDPOINT_FIXTURES
        ],
    }


def _asset_snapshot(asset: dict[str, Any]) -> dict[str, object]:
    """資産から生成対象のフィールドだけを抜き出す。"""
    return {
        "schema_version": asset["schema_version"],
        "provisional": asset["provisional"],
        "superseded_by": asset["superseded_by"],
        "source_digest": asset["source_digest"],
        "application_role": asset["application_role"],
        "protected_objects": asset["protected_objects"],
        "dangerous_endpoint_fixtures": asset["dangerous_endpoint_fixtures"],
    }


def _contract_state_violations(
    *,
    product_exists: bool,
    provisional_exists: bool,
    generated_provisional: bool,
    generated_source_asset: str,
    generated_superseded_by: str | None,
) -> set[str]:
    """製品資産の存在を切替条件として二状態違反を返す。"""
    violations: set[str] = set()
    if product_exists:
        if provisional_exists:
            violations.add("PROVISIONAL_ASSET_REMAINS")
        if generated_provisional:
            violations.add("GENERATED_MODULE_IS_PROVISIONAL")
        if generated_source_asset != _PRODUCT_ASSET.as_posix():
            violations.add("GENERATED_MODULE_REFERENCES_PROVISIONAL")
        if generated_superseded_by is not None:
            violations.add("GENERATED_MODULE_HAS_SUPERSEDED_BY")
        return violations

    if not provisional_exists:
        violations.add("PROVISIONAL_ASSET_MISSING")
    if not generated_provisional:
        violations.add("GENERATED_MODULE_IS_NOT_PROVISIONAL")
    if generated_source_asset != _PROVISIONAL_ASSET.as_posix():
        violations.add("GENERATED_MODULE_SOURCE_MISMATCH")
    if generated_superseded_by != _PRODUCT_ASSET.as_posix():
        violations.add("GENERATED_MODULE_SUPERSEDED_BY_MISMATCH")
    return violations


def test_generated_runtime_contract_matches_active_asset() -> None:
    """存在条件で選ばれた資産と配布対象モジュールが完全一致することを確認する。"""
    asset_path, asset = _active_asset_contract()

    assert asset["source_digest"] == _asset_digest(asset)
    assert runtime_contract.SOURCE_ASSET == asset_path.as_posix()
    assert _generated_snapshot() == _asset_snapshot(asset)


def test_dangerous_endpoint_fixture_categories_are_exact_set() -> None:
    """危険終点の各カテゴリに対応する負例が過不足なく存在することを確認する。"""
    fixture_rows = runtime_contract.DANGEROUS_ENDPOINT_FIXTURES

    assert {category for category, _ in fixture_rows} == (
        _DANGEROUS_ENDPOINT_CATEGORIES
    )
    assert len({fixture_id for _, fixture_id in fixture_rows}) == len(fixture_rows)


def test_role_attributes_and_protected_identifiers_are_closed_sets() -> None:
    """全7属性と保護対象の物理識別子を閉集合として検査する。"""
    attributes = asdict(runtime_contract.APPLICATION_ROLE_ATTRIBUTES)
    schema_manifest = _read_json_object(_REPOSITORY_ROOT / _SCHEMA_MANIFEST)
    manifest_tables = schema_manifest.get("tables")
    if not isinstance(manifest_tables, list):
        raise AssertionError("schema manifest の tables が配列でない")
    expected_tables = {
        ("public", str(row["name"]))
        for row in manifest_tables
        if isinstance(row, dict) and "name" in row
    }

    assert set(attributes) == _ROLE_ATTRIBUTE_NAMES
    assert set(runtime_contract.PROTECTED_SCHEMAS) == {"public"}
    assert set(runtime_contract.PROTECTED_TABLES) == expected_tables
    assert runtime_contract.PROTECTED_FUNCTIONS
    assert len(set(runtime_contract.PROTECTED_FUNCTIONS)) == len(
        runtime_contract.PROTECTED_FUNCTIONS
    )


def test_repository_uses_state_selected_by_product_asset_presence() -> None:
    """製品資産の存在そのものが暫定契約の切替条件になることを確認する。"""
    product_exists = (_REPOSITORY_ROOT / _PRODUCT_ASSET).exists()
    violations = _contract_state_violations(
        product_exists=product_exists,
        provisional_exists=(_REPOSITORY_ROOT / _PROVISIONAL_ASSET).exists(),
        generated_provisional=runtime_contract.PROVISIONAL,
        generated_source_asset=runtime_contract.SOURCE_ASSET,
        generated_superseded_by=runtime_contract.SUPERSEDED_BY,
    )

    assert violations == set()


def test_product_asset_rejects_provisional_asset_and_generated_reference() -> None:
    """製品資産追加後に暫定値が残る変異をすべて拒否する。"""
    violations = _contract_state_violations(
        product_exists=True,
        provisional_exists=True,
        generated_provisional=True,
        generated_source_asset=_PROVISIONAL_ASSET.as_posix(),
        generated_superseded_by=_PRODUCT_ASSET.as_posix(),
    )

    assert violations == {
        "PROVISIONAL_ASSET_REMAINS",
        "GENERATED_MODULE_IS_PROVISIONAL",
        "GENERATED_MODULE_REFERENCES_PROVISIONAL",
        "GENERATED_MODULE_HAS_SUPERSEDED_BY",
    }


@pytest.mark.parametrize(
    "field",
    (
        "schema_version",
        "provisional",
        "superseded_by",
        "source_digest",
        "application_role",
        "protected_objects",
        "dangerous_endpoint_fixtures",
    ),
)
def test_each_stale_generated_field_is_red(field: str) -> None:
    """生成対象の各フィールドが古い変異を一致検査で検出する。"""
    _, asset = _active_asset_contract()
    expected = _asset_snapshot(asset)
    generated = _generated_snapshot()
    generated[field] = object()

    assert generated != expected
