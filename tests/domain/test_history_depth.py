"""design.md §5 の履歴深さ導出と値域 schema を検査する。"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSET_PATH = ROOT / "backend/domain/history-depth.json"
VOCABULARY_PATH = ROOT / "backend/domain/vocabulary.schema.json"
TRIGGERS_PATH = ROOT / "backend/domain/review-triggers.json"

TOP_LEVEL_KEYS = {
    "version",
    "authorities",
    "derivation",
    "caseSets",
    "historyDepthPlusOne",
    "valueRangeSchema",
    "manualReview",
}
COMPOSITION_CASE_IDS = {
    "top-confirmed-play",
    "top-state-correction",
    "top-and-second-different",
    "all-elements-same-kind",
}
PRINCIPAL_FLAG_IDS = {
    "inning",
    "half",
    "score",
    "count",
    "outs",
    "battingOrder",
    "runners",
    "tiebreakActive",
    "gameEnded",
}
PRIMITIVE_DEFINITIONS = {
    "fixed-decimal": "FixedDecimal",
    "percentage": "Percentage",
    "mixed-fraction": "MixedFraction",
    "null-substitute": "NullSubstitute",
}
LINE_NUMBER_REFERENCE_PATTERN = re.compile(r":\d+")


@pytest.fixture(scope="module")
def asset() -> dict[str, Any]:
    """履歴深さ資産を読み込む。"""
    return json.loads(ASSET_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def vocabulary() -> dict[str, Any]:
    """ステップ 1 の表示語彙 schema を読み込む。"""
    return json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def triggers() -> dict[str, Any]:
    """見直しトリガーの評価レコードを読み込む。"""
    return json.loads(TRIGGERS_PATH.read_text(encoding="utf-8"))


def _section_text(source_text: str, section_heading: str) -> str:
    """指定見出しに属する本文を取り出す。

    Args:
        source_text: Markdown 正本の全文。
        section_heading: `#` を含む見出しの逐語。

    Returns:
        指定見出しから次の同階層以上の見出し直前までの文字列。
    """
    lines = source_text.splitlines()
    try:
        start = lines.index(section_heading)
    except ValueError as error:
        raise AssertionError(f"正本に節見出しがありません: {section_heading}") from error

    level = len(section_heading) - len(section_heading.lstrip("#"))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        heading = re.match(r"^(#+)\s", lines[index])
        if heading is not None and len(heading.group(1)) <= level:
            end = index
            break
    return "\n".join(lines[start:end])


def _derive_history_depth(candidate: dict[str, Any]) -> int:
    """case 集合から検査上限を一意に導出する。

    Args:
        candidate: 履歴深さ資産。

    Returns:
        必須シナリオ長と構成等価分割の最小深さの最大値。
    """
    assert set(candidate) == TOP_LEVEL_KEYS
    assert candidate["version"] == 1
    derivation = candidate["derivation"]
    assert set(derivation) == {
        "requiredScenarioCases",
        "stackCompositionCases",
        "formula",
        "result",
    }

    scenario_cases = derivation["requiredScenarioCases"]
    assert scenario_cases, "必須シナリオ case が空"
    scenario_lengths: list[int] = []
    fr040_independent_lengths: list[int] = []
    for scenario in scenario_cases:
        assert set(scenario) == {"id", "requiresFr040", "events", "length"}
        measured_length = len(scenario["events"])
        assert scenario["length"] == measured_length, (
            f"case {scenario['id']} の宣言長とイベント数が不一致"
        )
        assert measured_length > 0
        scenario_lengths.append(measured_length)
        if not scenario["requiresFr040"]:
            fr040_independent_lengths.append(measured_length)

    required_scenario_maximum = max(scenario_lengths)
    assert fr040_independent_lengths, "FR-040 抜きで成立する必須 case が無い"
    assert max(fr040_independent_lengths) == required_scenario_maximum, (
        "履歴深さの下限が FR-040 を含む case だけに依存している"
    )

    composition_cases = derivation["stackCompositionCases"]
    actual_composition_ids = {case["id"] for case in composition_cases}
    assert len(composition_cases) == 4
    assert actual_composition_ids == COMPOSITION_CASE_IDS
    composition_depths: list[int] = []
    for composition in composition_cases:
        assert set(composition) == {"id", "stackKinds", "minimumDepth"}
        measured_depth = len(composition["stackKinds"])
        assert composition["minimumDepth"] == measured_depth
        assert measured_depth > 0
        composition_depths.append(measured_depth)

    by_id = {case["id"]: case["stackKinds"] for case in composition_cases}
    assert by_id["top-confirmed-play"][0] == "confirmed-play"
    assert by_id["top-state-correction"][0] == "state-correction"
    different = by_id["top-and-second-different"]
    assert len(different) >= 2 and different[0] != different[1]
    same = by_id["all-elements-same-kind"]
    assert len(same) >= 2 and len(set(same)) == 1

    formula = derivation["formula"]
    assert formula == {
        "operator": "max",
        "operands": [
            {
                "cases": "requiredScenarioCases",
                "measure": "events.length",
                "aggregate": "max",
            },
            {
                "cases": "stackCompositionCases",
                "measure": "stackKinds.length",
                "aggregate": "max",
            },
        ],
    }
    composition_minimum_depth = max(composition_depths)
    derived_depth = max(required_scenario_maximum, composition_minimum_depth)
    assert derivation["result"] == {
        "requiredScenarioMaximum": required_scenario_maximum,
        "stackCompositionMinimumDepth": composition_minimum_depth,
        "historyDepth": derived_depth,
    }
    return derived_depth


def _resolved_case_value(case: dict[str, Any], history_depth: int) -> int:
    """case のリテラルまたは導出参照を具体値へ解決する。"""
    if "value" in case:
        assert set(case) == {"id", "value"}
        return case["value"]
    assert set(case) == {"id", "valueFrom"}
    references = {
        "historyDepth": history_depth,
        "historyDepthPlusOne": history_depth + 1,
    }
    assert case["valueFrom"] in references
    return references[case["valueFrom"]]


def _assert_case_sets_are_complete(candidate: dict[str, Any]) -> None:
    """深さ・構成・シナリオ長の全 case 集合を検査する。"""
    history_depth = _derive_history_depth(candidate)
    case_sets = candidate["caseSets"]
    assert set(case_sets) == {"depth", "composition", "scenarioLength"}

    depth_values = {
        _resolved_case_value(case, history_depth) for case in case_sets["depth"]
    }
    assert len(case_sets["depth"]) == 4
    assert depth_values == {0, 1, 2, history_depth}

    composition_ids = case_sets["composition"]
    assert len(composition_ids) == 4
    assert set(composition_ids) == COMPOSITION_CASE_IDS

    scenario_lengths = {
        _resolved_case_value(case, history_depth) for case in case_sets["scenarioLength"]
    }
    assert len(case_sets["scenarioLength"]) == 4
    assert scenario_lengths == {1, 2, history_depth, history_depth + 1}


def _assert_authority_verbatim_exists(candidate: dict[str, Any]) -> None:
    """FR-006 補足の逐語が指定節に実在することを検査する。"""
    authorities = candidate["authorities"]
    assert set(authorities) == {"historyRule", "historyCases", "displayParameters"}
    rule = authorities["historyRule"]
    assert set(rule) == {"id", "source", "section", "verbatim"}
    assert rule["id"] == "FR-006 補足"
    assert rule["source"] == "docs/requirements/requirements-pitchlog-2026-07-22.md"
    source_text = (ROOT / rule["source"]).read_text(encoding="utf-8")
    section_text = _section_text(source_text, rule["section"])
    assert rule["verbatim"] in section_text, "FR-006 補足の逐語が指定節に無い"

    serialized = json.dumps(candidate, ensure_ascii=False)
    assert LINE_NUMBER_REFERENCE_PATTERN.search(serialized) is None


def _assert_schema_node_has_value_domain(node: dict[str, Any], path: str) -> None:
    """主要フラグの schema 葉が空でない値域を持つことを検査する。"""
    if "enum" in node:
        assert node["enum"], f"{path} の enum が空"
        return
    node_type = node.get("type")
    if node_type == "boolean":
        return
    if node_type == "integer":
        assert "minimum" in node and "maximum" in node, f"{path} の整数境界が無い"
        assert node["minimum"] <= node["maximum"]
        return
    if node_type == "object":
        properties = node.get("properties", {})
        assert node.get("additionalProperties") is False
        assert properties and set(node.get("required", [])) == set(properties)
        for name, child in properties.items():
            _assert_schema_node_has_value_domain(child, f"{path}.{name}")
        return
    raise AssertionError(f"{path} に値域が無い")


def _assert_principal_flag_ranges(candidate: dict[str, Any]) -> None:
    """主要フラグ 9 項目の閉じた値域を検査する。"""
    value_schema = candidate["valueRangeSchema"]
    assert value_schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert value_schema["type"] == "object"
    assert value_schema["additionalProperties"] is False
    assert set(value_schema["required"]) == {
        "principalFlags",
        "displayPrimitiveParameters",
    }
    assert set(value_schema["properties"]) == set(value_schema["required"])

    flag_schema = value_schema["properties"]["principalFlags"]
    flag_properties = flag_schema["properties"]
    assert len(flag_properties) == 9
    assert set(flag_properties) == PRINCIPAL_FLAG_IDS
    assert set(flag_schema["required"]) == PRINCIPAL_FLAG_IDS
    assert flag_schema["additionalProperties"] is False
    for flag_id, node in flag_properties.items():
        _assert_schema_node_has_value_domain(node, flag_id)


def _parameter_schema_from_vocabulary(
    vocabulary_schema: dict[str, Any], definition_name: str
) -> dict[str, Any]:
    """語彙 schema の primitive 定義からパラメータ部分を導出する。"""
    parameter_schema = copy.deepcopy(vocabulary_schema["$defs"][definition_name])
    parameter_schema.pop("description", None)
    parameter_schema["required"].remove("kind")
    parameter_schema["properties"].pop("kind")
    return parameter_schema


def _assert_display_parameter_ranges(
    candidate: dict[str, Any], vocabulary_schema: dict[str, Any]
) -> None:
    """表示 primitive の全パラメータ値域を語彙 schema と突合する。"""
    schema = candidate["valueRangeSchema"]["properties"]["displayPrimitiveParameters"]
    actual = schema["properties"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert len(actual) == 4
    assert set(actual) == set(PRIMITIVE_DEFINITIONS)
    assert set(schema["required"]) == set(PRIMITIVE_DEFINITIONS)

    expected = {
        primitive_id: _parameter_schema_from_vocabulary(vocabulary_schema, definition_name)
        for primitive_id, definition_name in PRIMITIVE_DEFINITIONS.items()
    }
    assert actual == expected


def _assert_d_plus_one_contract(candidate: dict[str, Any]) -> None:
    """D+1 が実行可能性だけを保証することを検査する。"""
    history_depth = _derive_history_depth(candidate)
    contract = candidate["historyDepthPlusOne"]
    assert set(contract) == {"valueFrom", "guarantees", "requiresOutputEquivalence"}
    assert contract["valueFrom"] == "historyDepthPlusOne"
    assert contract["guarantees"] == ["execute", "not-rejected", "not-truncated"]
    assert contract["requiresOutputEquivalence"] is False

    boundary_case = {
        "id": "outside-guarantee-boundary",
        "valueFrom": contract["valueFrom"],
    }
    assert _resolved_case_value(boundary_case, history_depth) == history_depth + 1


def test_history_depth_is_derived_from_cases_and_maximum(asset: dict[str, Any]) -> None:
    _derive_history_depth(asset)


def test_all_depth_composition_and_scenario_length_cases_are_fixed(
    asset: dict[str, Any],
) -> None:
    _assert_case_sets_are_complete(asset)


def test_fr006_supplement_exists_verbatim_in_its_section(asset: dict[str, Any]) -> None:
    _assert_authority_verbatim_exists(asset)


def test_all_nine_principal_flags_have_closed_value_ranges(asset: dict[str, Any]) -> None:
    _assert_principal_flag_ranges(asset)


def test_all_display_primitive_parameters_match_vocabulary_schema(
    asset: dict[str, Any], vocabulary: dict[str, Any]
) -> None:
    _assert_display_parameter_ranges(asset, vocabulary)


def test_d_plus_one_only_requires_execution_without_rejection_or_truncation(
    asset: dict[str, Any],
) -> None:
    _assert_d_plus_one_contract(asset)


def test_manual_meaning_review_remains_pending_for_named_po(asset: dict[str, Any]) -> None:
    assert asset["manualReview"] == {
        "subject": "導出の意味レビュー",
        "judge": "山田正輝",
        "status": "pending",
    }


def test_trigger_nine_records_unique_derivation_as_not_fired(
    asset: dict[str, Any], triggers: dict[str, Any]
) -> None:
    derived_values = {_derive_history_depth(asset)}
    assert len(derived_values) == 1
    trigger_nine = next(trigger for trigger in triggers["triggers"] if trigger["id"] == 9)
    assert trigger_nine["evidenceLocation"] == "backend/domain/history-depth.json"
    assert trigger_nine["evaluation"] == {"fired": False}

    trigger_one = next(trigger for trigger in triggers["triggers"] if trigger["id"] == 1)
    assert trigger_one["evaluation"] is None


def test_fr040_only_lower_bound_is_rejected(asset: dict[str, Any]) -> None:
    mutated = copy.deepcopy(asset)
    for scenario in mutated["derivation"]["requiredScenarioCases"]:
        scenario["requiresFr040"] = True

    with pytest.raises(AssertionError, match="FR-040"):
        _derive_history_depth(mutated)


def test_literal_history_depth_disagreeing_with_cases_is_rejected(
    asset: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(asset)
    mutated["derivation"]["result"]["historyDepth"] += 1

    with pytest.raises(AssertionError):
        _derive_history_depth(mutated)


def test_missing_principal_flag_range_is_rejected(asset: dict[str, Any]) -> None:
    mutated = copy.deepcopy(asset)
    flags = mutated["valueRangeSchema"]["properties"]["principalFlags"]
    flags["properties"].pop("inning")
    flags["required"].remove("inning")

    with pytest.raises(AssertionError):
        _assert_principal_flag_ranges(mutated)


def test_d_plus_one_output_equivalence_requirement_is_rejected(
    asset: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(asset)
    mutated["historyDepthPlusOne"]["requiresOutputEquivalence"] = True

    with pytest.raises(AssertionError):
        _assert_d_plus_one_contract(mutated)


def test_one_character_change_to_fr006_verbatim_is_rejected(
    asset: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(asset)
    verbatim = mutated["authorities"]["historyRule"]["verbatim"]
    mutated["authorities"]["historyRule"]["verbatim"] = verbatim.replace(
        "対象は常に", "対象は必ず", 1
    )

    with pytest.raises(AssertionError, match="逐語"):
        _assert_authority_verbatim_exists(mutated)
