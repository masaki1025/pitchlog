"""製品 capability カタログの生成一致と全単射を検査する。"""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitchlog.authz.capability_catalog import (
    CapabilityCatalogError,
    generate_capability_catalog,
    validate_capability_catalog,
)
from pitchlog.authz.classification import load_json_object

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_CLASSIFICATION_PATH = (
    _REPOSITORY_ROOT / "contracts" / "authz" / "product" / "table-classification.json"
)
_CATALOG_PATH = (
    _REPOSITORY_ROOT / "contracts" / "authz" / "product" / "capability-catalog.json"
)
_EXPECTED_OPERATIONS_BY_PROFILE = {
    "tenant_owned": {"read", "insert", "update"},
    "self_tenant_row": {"read"},
    "effective_group_control": set(),
    "global_read_only": {"read"},
    "function_only": set(),
}


@pytest.fixture(scope="module")
def documents() -> tuple[dict[str, Any], dict[str, Any]]:
    """生成元の表分類と検査対象カタログを読み込む。"""
    return load_json_object(_CLASSIFICATION_PATH), load_json_object(_CATALOG_PATH)


def _classification_rows(classification: dict[str, Any]) -> list[dict[str, Any]]:
    """表分類の行を型付きで返す。"""
    rows = classification["tables"]
    assert isinstance(rows, list)
    assert all(isinstance(row, dict) for row in rows)
    return rows


def _capability_rows(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    """Capability カタログの行を型付きで返す。"""
    rows = catalog["capabilities"]
    assert isinstance(rows, list)
    assert all(isinstance(row, dict) for row in rows)
    return rows


def _row_for_table_operation(
    catalog: dict[str, Any],
    table_id: str,
    operation: str,
) -> dict[str, Any]:
    """指定した表と操作の行を一意に返す。"""
    rows = [
        row
        for row in _capability_rows(catalog)
        if row.get("table_id") == table_id and row.get("operation") == operation
    ]
    assert len(rows) == 1
    return rows[0]


def _table_with_profile(classification: dict[str, Any], profile: str) -> str:
    """指定したプロファイルから安定順で最初の表を返す。"""
    table_ids = sorted(
        row["table"]
        for row in _classification_rows(classification)
        if row["profile"] == profile
    )
    assert table_ids
    return table_ids[0]


def _assert_mutation_rejected(
    documents: tuple[dict[str, Any], dict[str, Any]],
    mutate: Callable[[dict[str, Any], dict[str, Any]], None],
) -> None:
    """改変前の green を表明してから資産変異が拒否されることを確かめる。"""
    classification, catalog = documents
    validate_capability_catalog(classification=classification, catalog=catalog)
    mutated_classification = copy.deepcopy(classification)
    mutated_catalog = copy.deepcopy(catalog)
    mutate(mutated_classification, mutated_catalog)
    with pytest.raises(CapabilityCatalogError):
        validate_capability_catalog(
            classification=mutated_classification,
            catalog=mutated_catalog,
        )


def _add_unclassified_row(
    _classification: dict[str, Any], catalog: dict[str, Any]
) -> None:
    """生成元にない表の行を追加する。"""
    _capability_rows(catalog).append(
        {
            "capability_id": "CAP:unclassified_table:read",
            "table_id": "unclassified_table",
            "operation": "read",
        }
    )


def _delete_row(_classification: dict[str, Any], catalog: dict[str, Any]) -> None:
    """生成済みの行を1件削除する。"""
    _capability_rows(catalog).pop(0)


def _change_operation(_classification: dict[str, Any], catalog: dict[str, Any]) -> None:
    """読み取り専用表の操作をスキーマ妥当な insert へ変更する。"""
    row = _row_for_table_operation(catalog, "tenants", "read")
    row["operation"] = "insert"
    row["capability_id"] = "CAP:tenants:insert"


def _duplicate_capability_id(
    _classification: dict[str, Any], catalog: dict[str, Any]
) -> None:
    """異なる2行に同じ capability ID を割り当てる。"""
    rows = _capability_rows(catalog)
    rows[1]["capability_id"] = rows[0]["capability_id"]


def _duplicate_table_operation(
    _classification: dict[str, Any], catalog: dict[str, Any]
) -> None:
    """同じ表と操作へ別の capability ID を追加する。"""
    source = _capability_rows(catalog)[0]
    _capability_rows(catalog).append(
        {
            "capability_id": f"CAP-ALIAS:{source['table_id']}:{source['operation']}",
            "table_id": source["table_id"],
            "operation": source["operation"],
        }
    )


def _add_function_only_row(
    classification: dict[str, Any], catalog: dict[str, Any]
) -> None:
    """function_only の表へ直接 read capability を追加する。"""
    table_id = _table_with_profile(classification, "function_only")
    _capability_rows(catalog).append(
        {
            "capability_id": f"CAP:{table_id}:read",
            "table_id": table_id,
            "operation": "read",
        }
    )


def _add_effective_group_control_row(
    classification: dict[str, Any], catalog: dict[str, Any]
) -> None:
    """effective_group_control の表へ直接 read capability を追加する。"""
    table_id = _table_with_profile(classification, "effective_group_control")
    _capability_rows(catalog).append(
        {
            "capability_id": f"CAP:{table_id}:read",
            "table_id": table_id,
            "operation": "read",
        }
    )


_CATALOG_MUTATIONS = (
    pytest.param(_add_unclassified_row, id="row-added"),
    pytest.param(_delete_row, id="row-deleted"),
    pytest.param(_change_operation, id="operation-changed"),
    pytest.param(_duplicate_capability_id, id="capability-id-duplicated"),
    pytest.param(_duplicate_table_operation, id="table-operation-duplicated"),
    pytest.param(_add_function_only_row, id="function-only-added"),
    pytest.param(
        _add_effective_group_control_row,
        id="effective-group-control-added",
    ),
)


def test_catalog_matches_deterministic_generator(
    documents: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """資産が表分類からの決定的な生成結果と一致する。"""
    classification, catalog = documents

    assert catalog == generate_capability_catalog(classification)
    validate_capability_catalog(classification=classification, catalog=catalog)


def test_generation_is_independent_of_classification_row_order(
    documents: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """表分類の行順を変えても生成結果が変わらない。"""
    classification, catalog = documents
    reordered = copy.deepcopy(classification)
    reordered["tables"] = list(reversed(_classification_rows(reordered)))

    assert generate_capability_catalog(reordered) == catalog


def test_only_direct_profile_operations_are_cataloged(
    documents: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """プロファイル定義から導いた direct 操作だけがカタログに載る。"""
    classification, catalog = documents
    profile_by_table = {
        row["table"]: row["profile"] for row in _classification_rows(classification)
    }
    expected_pairs = {
        (table_id, operation)
        for table_id, profile in profile_by_table.items()
        for operation in _EXPECTED_OPERATIONS_BY_PROFILE[profile]
    }
    actual_pairs = {
        (row["table_id"], row["operation"]) for row in _capability_rows(catalog)
    }

    assert actual_pairs == expected_pairs
    assert all(
        profile_by_table[row["table_id"]]
        not in {"effective_group_control", "function_only"}
        for row in _capability_rows(catalog)
    )
    assert {
        row["operation"]
        for row in _capability_rows(catalog)
        if profile_by_table[row["table_id"]] == "self_tenant_row"
    } == {"read"}
    assert {
        row["operation"]
        for row in _capability_rows(catalog)
        if profile_by_table[row["table_id"]] == "global_read_only"
    } == {"read"}


def test_capability_ids_and_table_operations_are_bijective(
    documents: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Capability ID と表・操作の組が全単射である。"""
    _classification, catalog = documents
    rows = _capability_rows(catalog)
    capability_ids = [row["capability_id"] for row in rows]
    table_operations = [(row["table_id"], row["operation"]) for row in rows]

    assert len(capability_ids) == len(set(capability_ids))
    assert len(table_operations) == len(set(table_operations))
    assert all(
        row["capability_id"] == f"CAP:{row['table_id']}:{row['operation']}"
        for row in rows
    )
    assert all(set(row) == {"capability_id", "table_id", "operation"} for row in rows)


@pytest.mark.parametrize("mutate", _CATALOG_MUTATIONS)
def test_catalog_mutation_is_rejected(
    documents: tuple[dict[str, Any], dict[str, Any]],
    mutate: Callable[[dict[str, Any], dict[str, Any]], None],
) -> None:
    """手書き変更と全単射・direct 境界を破る変異を拒否する。"""
    _assert_mutation_rejected(documents, mutate)
