"""ランタイム認可契約の生成一致と二状態切替を検査する。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from pitchlog.authz import runtime_contract
from pitchlog.authz.runtime_contract_state import (
    PRODUCT_ASSET,
    RUNTIME_CONTRACT_ASSET,
    STAGED_PRODUCT_ASSET,
    RuntimeContractState,
    derive_runtime_contract_fields,
    evaluate_repository,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
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


def _runtime_asset_contract() -> dict[str, Any]:
    """同じパスで製品化されるランタイム契約を読む。

    Returns:
        ランタイム契約 object。
    """
    return _read_json_object(_REPOSITORY_ROOT / RUNTIME_CONTRACT_ASSET)


def _generated_snapshot() -> dict[str, object]:
    """生成モジュールの公開契約を JSON と比較できる形へ変換する。"""
    return {
        "schema_version": runtime_contract.SCHEMA_VERSION,
        "runtime_contract_revision": runtime_contract.RUNTIME_CONTRACT_REVISION,
        "provisional": runtime_contract.PROVISIONAL,
        "superseded_by": runtime_contract.SUPERSEDED_BY,
        "derived_from": runtime_contract.DERIVED_FROM,
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
        "runtime_contract_revision": asset["runtime_contract_revision"],
        "provisional": asset["provisional"],
        "superseded_by": asset.get("superseded_by"),
        "derived_from": asset.get("derived_from"),
        "source_digest": asset["source_digest"],
        "application_role": asset["application_role"],
        "protected_objects": asset["protected_objects"],
        "dangerous_endpoint_fixtures": asset["dangerous_endpoint_fixtures"],
    }


def test_generated_runtime_contract_matches_active_asset() -> None:
    """同じパスの資産と配布対象モジュールが完全一致することを確認する。"""
    asset = _runtime_asset_contract()

    assert asset["source_digest"] == _asset_digest(asset)
    assert runtime_contract.SOURCE_ASSET == RUNTIME_CONTRACT_ASSET.as_posix()
    assert _generated_snapshot() == _asset_snapshot(asset)


def test_dangerous_endpoint_fixture_categories_are_exact_set() -> None:
    """危険終点の各カテゴリに対応する負例が過不足なく存在することを確認する。"""
    fixture_rows = runtime_contract.DANGEROUS_ENDPOINT_FIXTURES

    assert {category for category, _ in fixture_rows} == (
        _DANGEROUS_ENDPOINT_CATEGORIES
    )
    assert len({fixture_id for _, fixture_id in fixture_rows}) == len(fixture_rows)


def test_role_attributes_and_protected_identifiers_are_closed_sets() -> None:
    """全7属性と状態に応じた保護対象を閉集合として検査する。"""
    attributes = asdict(runtime_contract.APPLICATION_ROLE_ATTRIBUTES)
    state, violations = evaluate_repository(_REPOSITORY_ROOT)
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
    assert set(runtime_contract.PROTECTED_TABLES) == expected_tables
    assert runtime_contract.PROTECTED_FUNCTIONS
    assert len(set(runtime_contract.PROTECTED_FUNCTIONS)) == len(
        runtime_contract.PROTECTED_FUNCTIONS
    )
    assert violations == set()
    if state is RuntimeContractState.PRODUCT:
        derived = derive_runtime_contract_fields(
            _REPOSITORY_ROOT / PRODUCT_ASSET,
            _runtime_asset_contract(),
        )
        protected = derived["protected_objects"]
        assert list(runtime_contract.PROTECTED_SCHEMAS) == protected["schemas"]
        assert [list(value) for value in runtime_contract.PROTECTED_TABLES] == (
            protected["tables"]
        )
        assert [list(value) for value in runtime_contract.PROTECTED_FUNCTIONS] == (
            protected["functions"]
        )
    else:
        assert state in (
            RuntimeContractState.PROVISIONAL,
            RuntimeContractState.PENDING,
        )
        assert set(runtime_contract.PROTECTED_SCHEMAS) == {"public"}


def test_repository_state_and_predicates_are_evaluated_by_shared_api() -> None:
    """実リポジトリの状態と全述語が共有 API で green になることを確認する。"""
    state, violations = evaluate_repository(_REPOSITORY_ROOT)
    staged_exists = (_REPOSITORY_ROOT / STAGED_PRODUCT_ASSET).is_file()
    product_exists = (_REPOSITORY_ROOT / PRODUCT_ASSET).is_file()

    assert (state, staged_exists, product_exists) in {
        (RuntimeContractState.PROVISIONAL, False, False),
        (RuntimeContractState.PENDING, True, False),
        (RuntimeContractState.PRODUCT, False, True),
    }
    assert violations == set()


@pytest.mark.parametrize(
    "field",
    (
        "schema_version",
        "runtime_contract_revision",
        "provisional",
        "superseded_by",
        "derived_from",
        "source_digest",
        "application_role",
        "protected_objects",
        "dangerous_endpoint_fixtures",
    ),
)
def test_each_stale_generated_field_is_red(field: str) -> None:
    """生成対象の各フィールドが古い変異を一致検査で検出する。"""
    asset = _runtime_asset_contract()
    expected = _asset_snapshot(asset)
    generated = _generated_snapshot()
    generated[field] = object()

    assert generated != expected
