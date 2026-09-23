"""design.md §2 が定める機械条件の判定方法を検査する。"""

from __future__ import annotations

import copy
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONDITIONS_PATH = ROOT / "backend/domain/machine-conditions.json"
STEPS_PATH = ROOT / "docs/features/domain-calc-dsl/steps.json"

EXPECTED_TYPES = (
    ("section_scoped_diff", "節限定差分", "sibling-task"),
    ("same_commit", "同一コミット", "sibling-task"),
    ("zero_line_number_references", "行番号参照 0 件", "sibling-task"),
    ("population_measurement", "母集合計測", "sibling-task"),
    ("verbatim_presence", "文言存在", "sibling-task"),
    ("exit_code_separation", "exit コード分離", "domain-calc-dsl"),
    ("all_leaf_mutation", "全葉変異", "domain-calc-dsl"),
    ("set_difference", "集合差", "domain-calc-dsl"),
    ("independent_derivation", "独立導出", "domain-calc-dsl"),
    ("path_allowlist", "パス allowlist", "domain-calc-dsl"),
    ("history_precedes", "`history_precedes`", "domain-calc-dsl"),
    ("generated_provenance", "`generated_provenance`", "domain-calc-dsl"),
)
TYPE_KEYS = {
    "id",
    "name",
    "origin",
    "method",
    "positiveExample",
    "negativeExample",
}
EXAMPLE_KEYS = {"scenario", "expected"}
BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")


@pytest.fixture(scope="module")
def conditions() -> dict[str, Any]:
    """機械条件の型資産を読み込む。"""
    return json.loads(CONDITIONS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def steps() -> dict[str, Any]:
    """全ステップの単一定義を読み込む。"""
    return json.loads(STEPS_PATH.read_text(encoding="utf-8"))


def _validate_condition_asset(asset: dict[str, Any]) -> None:
    """型資産の閉包と正負例の完全性を検査する。"""
    assert set(asset) == {"version", "authority", "criteriaScan", "conditionTypes"}
    assert asset["version"] == 1
    assert asset["authority"] == "design.md §2 機械条件の判定方法"
    assert set(asset["criteriaScan"]) == {
        "source",
        "selector",
        "mechanicalMarker",
        "typeNameMarkup",
    }
    assert asset["criteriaScan"] == {
        "source": "docs/features/domain-calc-dsl/steps.json",
        "selector": "steps[].criteria",
        "mechanicalMarker": "`[機械]`",
        "typeNameMarkup": "Markdown の太字内にある型名の完全一致",
    }

    actual_types = {
        (condition["id"], condition["name"], condition["origin"])
        for condition in asset["conditionTypes"]
    }
    expected_types = set(EXPECTED_TYPES)
    missing_types = expected_types - actual_types
    unexpected_types = actual_types - expected_types
    assert not missing_types and not unexpected_types, (
        f"型の集合差: missing={sorted(missing_types)!r}, "
        f"unexpected={sorted(unexpected_types)!r}"
    )
    assert len(asset["conditionTypes"]) == 12

    missing_positive = {
        condition["name"]
        for condition in asset["conditionTypes"]
        if "positiveExample" not in condition
    }
    missing_negative = {
        condition["name"]
        for condition in asset["conditionTypes"]
        if "negativeExample" not in condition
    }
    assert not missing_positive, f"正例が無い型: {sorted(missing_positive)!r}"
    assert not missing_negative, f"負例が無い型: {sorted(missing_negative)!r}"

    malformed = {
        condition["name"]
        for condition in asset["conditionTypes"]
        if set(condition) != TYPE_KEYS
    }
    assert not malformed, f"型のキー集合が不正: {sorted(malformed)!r}"

    for condition in asset["conditionTypes"]:
        assert condition["method"]
        assert set(condition["positiveExample"]) == EXAMPLE_KEYS
        assert set(condition["negativeExample"]) == EXAMPLE_KEYS
        assert condition["positiveExample"]["scenario"]
        assert condition["positiveExample"]["expected"] == "pass"
        assert condition["negativeExample"]["scenario"]
        assert condition["negativeExample"]["expected"] == "fail"


def _extract_condition_type_names(
    steps_asset: dict[str, Any], candidates: set[str], mechanical_marker: str
) -> tuple[Counter[str], int]:
    """`[機械]` criteria の太字から候補と完全一致する型名を抽出する。"""
    found: Counter[str] = Counter()
    mechanical_criteria = 0
    for step in steps_asset["steps"]:
        criteria = step["criteria"]
        if mechanical_marker not in criteria:
            continue
        mechanical_criteria += 1
        found.update(name for name in BOLD_PATTERN.findall(criteria) if name in candidates)
    return found, mechanical_criteria


def _assert_scanned_types_are_known(found: set[str], allowed: set[str]) -> None:
    """走査で得た型名が空でなく許可集合内であることを検査する。"""
    assert found, "[機械] criteria から型名を 1 件も抽出できません"
    unknown = found - allowed
    assert not unknown, f"12 型に紐づかない型名: {sorted(unknown)!r}"


def test_machine_condition_asset_has_exactly_twelve_closed_types(
    conditions: dict[str, Any],
) -> None:
    _validate_condition_asset(conditions)


def test_machine_condition_asset_has_no_line_number_references(
    conditions: dict[str, Any],
) -> None:
    serialized = json.dumps(conditions, ensure_ascii=False)
    assert re.search(r":\d+", serialized) is None


def test_every_type_has_positive_and_negative_examples(conditions: dict[str, Any]) -> None:
    names = {condition["name"] for condition in conditions["conditionTypes"]}
    positive = {
        condition["name"]
        for condition in conditions["conditionTypes"]
        if condition.get("positiveExample")
    }
    negative = {
        condition["name"]
        for condition in conditions["conditionTypes"]
        if condition.get("negativeExample")
    }
    assert names - positive == set(), f"正例が無い型: {sorted(names - positive)!r}"
    assert names - negative == set(), f"負例が無い型: {sorted(names - negative)!r}"


def test_all_steps_machine_criteria_use_only_declared_types(
    conditions: dict[str, Any], steps: dict[str, Any]
) -> None:
    allowed = {condition["name"] for condition in conditions["conditionTypes"]}
    marker = conditions["criteriaScan"]["mechanicalMarker"]
    found, mechanical_criteria = _extract_condition_type_names(steps, allowed, marker)

    assert steps["expected_total"] == 57
    assert len(steps["steps"]) == 57
    assert mechanical_criteria == 57
    assert sum(found.values()) == 68
    assert len(found) == 10
    _assert_scanned_types_are_known(set(found), allowed)


def test_thirteenth_type_is_rejected(conditions: dict[str, Any]) -> None:
    mutated = copy.deepcopy(conditions)
    extra = copy.deepcopy(mutated["conditionTypes"][0])
    extra.update({"id": "unknown_type", "name": "未知の型", "origin": "domain-calc-dsl"})
    mutated["conditionTypes"].append(extra)

    with pytest.raises(AssertionError, match="未知の型"):
        _validate_condition_asset(mutated)


def test_type_without_negative_example_is_rejected(conditions: dict[str, Any]) -> None:
    mutated = copy.deepcopy(conditions)
    missing_name = mutated["conditionTypes"][7]["name"]
    del mutated["conditionTypes"][7]["negativeExample"]

    with pytest.raises(AssertionError, match=missing_name):
        _validate_condition_asset(mutated)


def test_unknown_condition_type_in_criteria_is_rejected(
    conditions: dict[str, Any], steps: dict[str, Any]
) -> None:
    mutated = copy.deepcopy(steps)
    unknown_name = "未知の判定型"
    mutated["steps"][0]["criteria"] += f" / **{unknown_name}**"
    allowed = {condition["name"] for condition in conditions["conditionTypes"]}
    marker = conditions["criteriaScan"]["mechanicalMarker"]
    found, _ = _extract_condition_type_names(mutated, allowed | {unknown_name}, marker)

    with pytest.raises(AssertionError, match=unknown_name):
        _assert_scanned_types_are_known(set(found), allowed)
