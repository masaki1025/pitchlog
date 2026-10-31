"""表分類から製品 capability カタログを決定的に導出する。"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import cast

CATALOG_SCHEMA_VERSION = 1
CLASSIFICATION_SOURCE = "contracts/authz/product/table-classification.json"
CAPABILITY_OPERATIONS = frozenset({"read", "insert", "update"})

_TABLE_ID_PATTERN = r"^[a-z_][a-z0-9_]*$"
_PROFILE_OPERATIONS = {
    "tenant_owned": ("read", "insert", "update"),
    "self_tenant_row": ("read",),
    "effective_group_control": (),
    "global_read_only": ("read",),
    "function_only": (),
}
_INITIAL_STORAGE_TABLES = frozenset(
    {
        "trusted_devices",
        "game_start_requests",
        "game_start_attempts",
        "recording_right_deliveries",
    }
)


class CapabilityCatalogError(ValueError):
    """分類または capability カタログの不正を表す。

    Attributes:
        violations: fail-closed で検出した違反の安定順列。
    """

    def __init__(self, violations: Iterable[str]) -> None:
        """空でない違反列を保持する。

        Args:
            violations: 検出した違反。
        """
        self.violations = tuple(violations)
        if not self.violations:
            raise ValueError("違反がない状態では例外を構築できない")
        super().__init__("capabilityカタログが不正:\n- " + "\n- ".join(self.violations))


def _object_rows(
    value: object,
    label: str,
    violations: list[str],
) -> tuple[dict[str, object], ...]:
    """文字列キーの object 配列を検証して返す。"""
    if not isinstance(value, list):
        violations.append(f"{label}はobject配列でなければならない")
        return ()
    rows: list[dict[str, object]] = []
    for index, raw_row in enumerate(value):
        if not isinstance(raw_row, dict) or not all(
            isinstance(key, str) for key in raw_row
        ):
            violations.append(f"{label}[{index}]は文字列キーのobjectでなければならない")
            continue
        rows.append(cast(dict[str, object], raw_row))
    return tuple(rows)


def _optional(value: Mapping[str, object], key: str) -> object:
    """Mapping の省略可能な値をメソッド呼び出しなしで返す。"""
    return value[key] if key in value else None


def _required_text(
    value: object,
    label: str,
    violations: list[str],
) -> str | None:
    """空でない文字列だけを返す。"""
    if not isinstance(value, str) or not value:
        violations.append(f"{label}は空でない文字列でなければならない")
        return None
    return value


def _classification_assignments(
    classification: Mapping[str, object],
) -> tuple[tuple[str, str], ...]:
    """表分類を検証し、表名順の割り当てへ正規化する。"""
    violations: list[str] = []
    expected_root_keys = frozenset({"schema_version", "tables"})
    if frozenset(classification) != expected_root_keys:
        violations.append(
            "table-classificationのキーが不一致: "
            f"期待={sorted(expected_root_keys)}, 実際={sorted(classification)}"
        )
    if _optional(classification, "schema_version") != 1:
        violations.append("table-classification.schema_versionは1でなければならない")

    assignments: dict[str, str] = {}
    for index, row in enumerate(
        _object_rows(
            _optional(classification, "tables"),
            "table-classification.tables",
            violations,
        )
    ):
        label = f"table-classification.tables[{index}]"
        table_id = _required_text(_optional(row, "table"), f"{label}.table", violations)
        profile = _required_text(
            _optional(row, "profile"), f"{label}.profile", violations
        )
        if table_id is not None and re.fullmatch(_TABLE_ID_PATTERN, table_id) is None:
            violations.append(f"{label}.tableが表IDの形式ではない: {table_id!r}")
        if profile not in _PROFILE_OPERATIONS:
            violations.append(f"{label}.profileが閉じた列挙にない: {profile!r}")
        if table_id is None or profile not in _PROFILE_OPERATIONS:
            continue
        if table_id in assignments:
            violations.append(f"表分類に表IDの重複がある: {table_id}")
            continue
        assignments[table_id] = profile

    if not assignments:
        violations.append("表分類から割り当てを1件も導出できない")
    if violations:
        raise CapabilityCatalogError(violations)
    return tuple(sorted(assignments.items()))


def _capability_id(table_id: str, operation: str) -> str:
    """表IDと操作から一意な capability ID を返す。"""
    return f"CAP:{table_id}:{operation}"


def _initial_storage_profile(classification: Mapping[str, object]) -> bool:
    """初期保存の完全な閉分類だけで世代INSERTの専用関数移管を認識する。"""
    violations: list[str] = []
    rows = _object_rows(
        _optional(classification, "tables"), "table-classification.tables", violations
    )
    reserved = {
        row["table"]: row
        for row in rows
        if isinstance(_optional(row, "table"), str)
        and row["table"] in _INITIAL_STORAGE_TABLES
    }
    marked = [
        row
        for row in rows
        if isinstance(_optional(row, "access_path"), dict)
        and cast(dict[str, object], row["access_path"]).get("reason")
        == "initial_right_storage"
    ]
    if not reserved and not marked:
        return False
    if (
        type(_optional(classification, "schema_version")) is not int
        or set(reserved) != _INITIAL_STORAGE_TABLES
        or len(marked) != len(_INITIAL_STORAGE_TABLES)
    ):
        violations.append("初期保存分類は固定4表の完全な組でなければならない")
    for table in sorted(_INITIAL_STORAGE_TABLES):
        expected = {
            "table": table,
            "profile": "function_only",
            "access_path": {
                "reason": "initial_right_storage",
                "owner_unit": "U-R1",
            },
        }
        actual = reserved.get(table)
        if (
            type(actual) is not dict
            or actual != expected
            or type(actual.get("access_path")) is not dict
        ):
            violations.append(f"{table}: 初期保存の閉分類と一致しない")
    generation = [
        row for row in rows if _optional(row, "table") == "recording_generations"
    ]
    if len(generation) != 1 or generation[0] != {
        "table": "recording_generations",
        "profile": "tenant_owned",
    }:
        violations.append("初期保存でも記録権世代の既存tenant_owned分類が必要")
    if violations:
        raise CapabilityCatalogError(violations)
    return True


def generate_capability_catalog(
    classification: Mapping[str, object],
) -> dict[str, object]:
    """表分類から閉じた capability カタログを生成する。

    Args:
        classification: ``table-classification.json`` の JSON object。

    Returns:
        表ID順、同一表内は read・insert・update 順のカタログ。

    Raises:
        CapabilityCatalogError: 表分類を安全に解釈できない場合。
    """
    assignments = _classification_assignments(classification)
    initial_storage = _initial_storage_profile(classification)
    capabilities: list[dict[str, str]] = []
    for table_id, profile in assignments:
        for operation in _PROFILE_OPERATIONS[profile]:
            if initial_storage and (table_id, operation) == (
                "recording_generations",
                "insert",
            ):
                continue
            capabilities.append(
                {
                    "capability_id": _capability_id(table_id, operation),
                    "table_id": table_id,
                    "operation": operation,
                }
            )
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "source_classification": CLASSIFICATION_SOURCE,
        "capabilities": capabilities,
    }


def validate_capability_catalog(
    *,
    classification: Mapping[str, object],
    catalog: Mapping[str, object],
) -> None:
    """カタログの形式、全単射、生成結果との一致を検査する。

    Args:
        classification: 生成元の表分類 JSON object。
        catalog: 検査対象の capability カタログ JSON object。

    Raises:
        CapabilityCatalogError: カタログが生成結果と一致しない場合。
    """
    expected = generate_capability_catalog(classification)
    violations: list[str] = []
    expected_root_keys = frozenset(
        {"schema_version", "source_classification", "capabilities"}
    )
    if frozenset(catalog) != expected_root_keys:
        violations.append(
            "capability-catalogのキーが不一致: "
            f"期待={sorted(expected_root_keys)}, 実際={sorted(catalog)}"
        )
    if _optional(catalog, "schema_version") != CATALOG_SCHEMA_VERSION:
        violations.append(
            f"capability-catalog.schema_versionは{CATALOG_SCHEMA_VERSION}"
            "でなければならない"
        )
    if _optional(catalog, "source_classification") != CLASSIFICATION_SOURCE:
        violations.append(
            "capability-catalog.source_classificationが生成元を指していない"
        )

    capability_ids: list[str] = []
    table_operations: list[tuple[str, str]] = []
    for index, row in enumerate(
        _object_rows(
            _optional(catalog, "capabilities"),
            "capability-catalog.capabilities",
            violations,
        )
    ):
        label = f"capability-catalog.capabilities[{index}]"
        expected_row_keys = frozenset({"capability_id", "table_id", "operation"})
        if frozenset(row) != expected_row_keys:
            violations.append(
                f"{label}のキーが不一致: 期待={sorted(expected_row_keys)}, "
                f"実際={sorted(row)}"
            )
        capability_id = _required_text(
            _optional(row, "capability_id"), f"{label}.capability_id", violations
        )
        table_id = _required_text(
            _optional(row, "table_id"), f"{label}.table_id", violations
        )
        operation = _required_text(
            _optional(row, "operation"), f"{label}.operation", violations
        )
        if operation not in CAPABILITY_OPERATIONS:
            violations.append(f"{label}.operationが閉じた列挙にない: {operation!r}")
        if capability_id is None or table_id is None or operation is None:
            continue
        capability_ids.append(capability_id)
        table_operations.append((table_id, operation))
        deterministic_id = _capability_id(table_id, operation)
        if capability_id != deterministic_id:
            violations.append(
                f"{label}.capability_idが決定的なIDと一致しない: "
                f"期待={deterministic_id!r}, 実際={capability_id!r}"
            )

    if len(capability_ids) != len(set(capability_ids)):
        violations.append("capability IDに重複がある")
    if len(table_operations) != len(set(table_operations)):
        violations.append("(表ID, 操作種別)に重複がある")

    expected_rows = expected["capabilities"]
    if not isinstance(expected_rows, list):
        raise AssertionError("生成器のcapabilitiesは配列でなければならない")
    expected_pairs = {
        (row["table_id"], row["operation"])
        for row in expected_rows
        if isinstance(row, dict)
    }
    actual_pairs = set(table_operations)
    if actual_pairs != expected_pairs:
        violations.append(
            "許可された(表ID, 操作種別)が不一致: "
            f"不足={sorted(expected_pairs - actual_pairs)}, "
            f"余分={sorted(actual_pairs - expected_pairs)}"
        )
    if catalog != expected:
        violations.append("capabilityカタログが表分類からの生成結果と一致しない")
    if violations:
        raise CapabilityCatalogError(violations)
