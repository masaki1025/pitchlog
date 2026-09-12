"""DB を使わずに型境界の正本・manifest 契約を検査する。"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from type_boundary_contract import (
    MIGRATION_EVENT_PAYLOAD_DEFINITION,
    ColumnContract,
    destination_columns,
    four_shape_violations,
    legacy_storage_types,
    payload_contract_violations,
    play_row_type_violations,
    raw_payload_round_trip_violations,
    regular_schema_violations,
    sentinel_conversion_hits,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPOSITORY_ROOT / "contracts" / "db" / "schema-manifest.json"
_DATA_MODEL_PATH = _REPOSITORY_ROOT / "docs" / "design" / "data-model.md"
_DATA_LAYER_PATH = _REPOSITORY_ROOT / "docs" / "legacy" / "research" / "data-layer.md"
_PRODUCT_SOURCE_ROOT = _REPOSITORY_ROOT / "backend" / "src"


def _load_manifest() -> dict[str, object]:
    """実ファイルの manifest を object として返す。"""
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def _manifest_table(manifest: dict[str, object], name: str) -> dict[str, object]:
    """Manifest から名前が一致する表を一意に返す。"""
    tables = manifest["tables"]
    if not isinstance(tables, list):
        raise AssertionError("manifest.tables が配列ではない")
    matches = [
        table
        for table in tables
        if isinstance(table, dict) and table.get("name") == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"manifest の表を一意に解決できない: {name}")
    return matches[0]


def _manifest_column(table: dict[str, object], name: str) -> ColumnContract:
    """Manifest 表から型境界用の列構造を返す。"""
    columns = table["columns"]
    if not isinstance(columns, list):
        raise AssertionError("manifest の columns が配列ではない")
    matches = [
        column
        for column in columns
        if isinstance(column, dict) and column.get("name") == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"manifest の列を一意に解決できない: {name}")
    column = matches[0]
    data_type = column.get("type")
    nullable = column.get("nullable")
    default = column.get("default")
    if not isinstance(data_type, str) or not isinstance(nullable, bool):
        raise AssertionError(f"manifest の列構造が不正: {name}")
    if default is not None and not isinstance(default, str):
        raise AssertionError(f"manifest の列既定値が不正: {name}")
    return ColumnContract(data_type, nullable, default)


def test_migration_event_payload_matches_canonical_destination_categories() -> None:
    """B1〜B4 を正本の区分表と manifest 宣言から機械検査する。"""
    manifest = _load_manifest()
    destination_entries = manifest["legacy_destination_categories"]
    if not isinstance(destination_entries, list):
        raise AssertionError("legacy_destination_categories が配列ではない")
    manifest_categories = {
        str(entry["category"])
        for entry in destination_entries
        if isinstance(entry, dict)
    }
    destinations = destination_columns(_DATA_MODEL_PATH.read_text(encoding="utf-8"))
    payload = _manifest_column(_manifest_table(manifest, "operation_events"), "payload")

    assert set().union(*destinations.values()) == set(range(88))
    assert (
        payload_contract_violations(
            destinations,
            MIGRATION_EVENT_PAYLOAD_DEFINITION,
            manifest_categories,
            payload,
        )
        == []
    )


@pytest.mark.parametrize(
    ("definition", "payload", "message"),
    [
        (
            replace(MIGRATION_EVENT_PAYLOAD_DEFINITION, held_only_columns=frozenset()),
            ColumnContract("jsonb", False, None),
            "保持のみ列とペイロード区分定義が一致しない",
        ),
        (
            replace(
                MIGRATION_EVENT_PAYLOAD_DEFINITION,
                held_only_columns=frozenset({10, 72}),
            ),
            ColumnContract("jsonb", False, None),
            "導出の列がペイロード区分定義へ混入: [10]",
        ),
        (
            replace(
                MIGRATION_EVENT_PAYLOAD_DEFINITION,
                retained_schema_categories=(
                    MIGRATION_EVENT_PAYLOAD_DEFINITION.retained_schema_categories
                    | {"移行時に使用"}
                ),
            ),
            ColumnContract("jsonb", False, None),
            "移行時に使用の区分が新スキーマ保持区分へ残っている",
        ),
        (
            MIGRATION_EVENT_PAYLOAD_DEFINITION,
            ColumnContract("text", False, None),
            "operation_events.payload が jsonb NOT NULL・既定値なしではない",
        ),
    ],
)
def test_broken_payload_category_contract_is_detected(
    definition: object, payload: ColumnContract, message: str
) -> None:
    """B1〜B4 の壊れた定義が純関数で red になることを示す。"""
    if not isinstance(definition, type(MIGRATION_EVENT_PAYLOAD_DEFINITION)):
        raise AssertionError("テスト用ペイロード定義の型が不正")
    manifest = _load_manifest()
    entries = manifest["legacy_destination_categories"]
    if not isinstance(entries, list):
        raise AssertionError("legacy_destination_categories が配列ではない")
    categories = {
        str(entry["category"]) for entry in entries if isinstance(entry, dict)
    }
    violations = payload_contract_violations(
        destination_columns(_DATA_MODEL_PATH.read_text(encoding="utf-8")),
        definition,
        categories,
        payload,
    )
    assert message in violations


def test_product_code_has_no_field_sentinel_conversion(tmp_path: Path) -> None:
    """R-9 に従い backend/src 全体にセンチネル変換がないことを検査する。"""
    assert sentinel_conversion_hits(_PRODUCT_SOURCE_ROOT) == []
    synthetic_source = tmp_path / "legacy_value.py"
    synthetic_source.write_text(
        "def convert(value):\n    return None if value in (0, '0', '') else value\n",
        encoding="utf-8",
    )
    assert sentinel_conversion_hits(tmp_path) == [
        "legacy_value.py:2:センチネル比較から NULL を生成"
    ]


def test_raw_payload_negative_cases_are_detected_by_pure_functions() -> None:
    """A の部分潰しとバイト変化が純関数で red になることを示す。"""
    expected = {1: b'0|"0"|""|null', 2: b"\xff\xfe"}
    assert raw_payload_round_trip_violations(expected, {}) == [
        "隔離原本の行が不足: source_read_order=1",
        "隔離原本の行が不足: source_read_order=2",
    ]
    actual = {1: b'0|0|""|null', 2: b"\xff\xfe"}
    assert raw_payload_round_trip_violations(expected, actual) == [
        "隔離原本のバイト列が変化: source_read_order=1"
    ]
    assert four_shape_violations([0, 0, "", None]) != []


def _valid_regular_schema() -> dict[tuple[str, str], ColumnContract]:
    """C の純関数負例を作るための最小の正常構造を返す。"""
    return {
        ("play_rows", "raw_fielder_position"): ColumnContract("text", True, None),
        ("play_rows", "resolved_fielder_id"): ColumnContract("uuid", True, None),
        ("play_rows", "raw_error_position"): ColumnContract("text", True, None),
        ("play_rows", "resolved_error_player_id"): ColumnContract("uuid", True, None),
        ("migrated_final_lineups", "raw_lineup"): ColumnContract("text", False, None),
    }


def test_regular_schema_boundary_pure_reference_is_valid() -> None:
    """C の純関数が正常な原本/解決列境界を受理することを示す。"""
    source_types = legacy_storage_types(_DATA_LAYER_PATH.read_text(encoding="utf-8"))
    assert regular_schema_violations(_valid_regular_schema(), source_types) == []


def test_play_row_type_contract_detects_real_as_numeric_and_owns_uuid_exceptions() -> (
    None
):
    """REAL の numeric 化を拒否し、名寄せ列の uuid 例外を契約側で扱う。"""
    destination_numbers = frozenset({27, 42})
    source_columns = {27: "batter_id", 42: "course_x"}
    source_types = {27: "TEXT", 42: "REAL"}
    valid_columns = {
        ("play_rows", "batter_id"): ColumnContract("uuid", True, None),
        ("play_rows", "course_x"): ColumnContract("double precision", True, None),
    }

    assert (
        play_row_type_violations(
            destination_numbers, source_columns, valid_columns, source_types
        )
        == []
    )
    broken_columns = dict(valid_columns)
    broken_columns[("play_rows", "course_x")] = ColumnContract("numeric", True, None)
    assert play_row_type_violations(
        destination_numbers, source_columns, broken_columns, source_types
    ) == ["列 42 の型が旧保存型契約と不一致: course_x=numeric, 期待=double precision"]


@pytest.mark.parametrize(
    "defect", ["missing_raw", "numeric_raw", "filled_resolution", "final_resolution"]
)
def test_broken_regular_schema_boundary_is_detected(defect: str) -> None:
    """C1〜C4 の壊れた構造が純関数で red になることを示す。"""
    columns = _valid_regular_schema()
    if defect == "missing_raw":
        del columns[("play_rows", "raw_fielder_position")]
    elif defect == "numeric_raw":
        columns[("play_rows", "raw_fielder_position")] = ColumnContract(
            "integer", True, None
        )
    elif defect == "filled_resolution":
        columns[("play_rows", "resolved_fielder_id")] = ColumnContract(
            "uuid", False, "gen_random_uuid()"
        )
    else:
        columns[("migrated_final_lineups", "resolved_player_id")] = ColumnContract(
            "uuid", True, None
        )

    source_types = legacy_storage_types(_DATA_LAYER_PATH.read_text(encoding="utf-8"))
    assert regular_schema_violations(columns, source_types) != []
