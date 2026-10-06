"""状況判定と終了判定ケースの宣言規則適用とidentity変異を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load_module(name: str, path: Path) -> Any:
    """既存テストと同じ方法で検査器と依存モジュールを読む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


normalization = _load_module(
    "state_transition_normalization", SCRIPTS / "state_transition_normalization.py"
)
checker = _load_module(
    "check_state_transition_normalization", SCRIPTS / "check_state_transition_normalization.py"
)


def _asset(name: str) -> dict[str, Any]:
    """状況判定資産を独立した値として読む。"""
    return json.loads(
        (ROOT / "contracts/state-transition" / name).read_text(encoding="utf-8")
    )


def _rules_for_schema(schema: dict[str, Any]) -> Any:
    """指定した規則宣言と現行の語彙資産からnormalizerを作る。"""
    vocabulary = json.loads(
        (ROOT / "contracts/vocabulary/input_vocabulary_v1.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (ROOT / "contracts/vocabulary/vocabulary_manifest_v1.json").read_text(encoding="utf-8")
    )
    return normalization.NormalizationRules(
        schema, vocabulary, manifest,
        checker.PurePosixPath("contracts/vocabulary/input_vocabulary_v1.json"),
    )


def test_all_cases_match_declared_normalization_rules() -> None:
    """状況判定96件と終了判定170件で宣言規則の適用結果が一致する。"""
    assert checker.check_repository(ROOT) == 266


def test_game_end_cases_have_triples_and_display_names_are_resolved() -> None:
    """終了判定170件の3点と表示名165件の安定ID化を確認する。"""
    cases, rules = checker.load_game_end_inputs(ROOT)
    assert len(cases) == 170
    assert all({"raw", "normalizationRuleId", "normalized"} <= set(case) for case in cases)
    assert checker.check_cases(cases, rules) == 170
    display_cases = [
        case for case in cases
        if case["normalizationRuleId"] == "game-end-result-display-name-to-id"
    ]
    assert len(display_cases) == 165
    assert all(case["normalized"] == case["inputCoordinate"] for case in cases)
    assert all(
        case["raw"]["event.perPitch.resultId"]
        != case["inputCoordinate"]["event.perPitch.resultId"]
        for case in display_cases
    )
    assert all(
        case["raw"] == case["normalized"] == case["inputCoordinate"]
        for case in cases if case["normalizationRuleId"] == "identity"
    )


@pytest.mark.parametrize(
    "contract", ["state_transition_contract_v1.json", "game_end_contract_v1.json"]
)
def test_input_coordinate_must_equal_normalized_in_both_contracts(contract: str) -> None:
    """どちらの契約でも座標が正規形から外れたら拒否する。"""
    cases = _asset(contract)["cases"]
    rules = checker.load_inputs(ROOT)[1]
    assert checker.check_cases(cases, rules) == len(cases)
    mutated = copy.deepcopy(next(case for case in cases if case["raw"] != case["normalized"]))
    mutated["inputCoordinate"] = copy.deepcopy(mutated["raw"])
    with pytest.raises(
        checker.NormalizationCheckError, match="inputCoordinateとnormalizedが不一致"
    ):
        checker.check_cases([mutated], rules)


def test_game_end_display_name_fails_when_rule_is_mutated_to_identity() -> None:
    """終了判定の表示名をidentityに変異すると突合が失敗する。"""
    cases, _ = checker.load_game_end_inputs(ROOT)
    case = next(
        item for item in cases
        if item["normalizationRuleId"] == "game-end-result-display-name-to-id"
    )
    schema = _asset("state_transition_contract_schema_v1.json")
    rule = next(
        item for item in schema["x-pitchlog-stage1-normalization"]["ruleCatalog"]
        if item["ruleId"] == case["normalizationRuleId"]
    )
    rule["transform"] = {"kind": "identity"}
    with pytest.raises(checker.NormalizationCheckError, match="event.perPitch.resultId"):
        checker.check_cases([case], _rules_for_schema(schema))


@pytest.mark.parametrize(
    ("case_id", "axis_value", "raw_result", "normalized_result"),
    [
        (
            "ST-MATRIX-07c1f26a645dae53", "batting-result",
            "見逃し", "batting-result.called-pitch",
        ),
        (
            "ST-MATRIX-d6f10ba77c4afebf", "secondary-result",
            "PB", "secondary-result.passed-ball",
        ),
    ],
)
def test_noncanonical_raw_fails_when_rule_is_mutated_to_identity(
    case_id: str, axis_value: str, raw_result: str, normalized_result: str
) -> None:
    """異なるcaseとeventKind軸値でnormalizerのidentity変異を拒否する。"""
    cases, _ = checker.load_inputs(ROOT)
    case = next(item for item in cases if item["caseId"] == case_id)
    assert case["raw"]["eventKind"] == axis_value
    assert case["raw"]["resultId"] == raw_result
    assert case["normalized"]["resultId"] == normalized_result
    schema = _asset("state_transition_contract_schema_v1.json")
    rule_id = case["normalizationRuleId"]
    rule = next(
        item for item in schema["x-pitchlog-stage1-normalization"]["ruleCatalog"]
        if item["ruleId"] == rule_id
    )
    assert rule["transform"]["kind"] == "vocabulary-lookup"
    rule["transform"] = {"kind": "identity"}
    with pytest.raises(checker.NormalizationCheckError, match="resultId") as error:
        checker.check_cases([case], _rules_for_schema(schema))
    assert case_id in str(error.value)
    assert "適用結果とnormalizedが不一致" in str(error.value)


def test_canonical_raw_with_identity_is_accepted() -> None:
    """正規形rawのidentityケース25件を拒否せず全件通す。"""
    cases, rules = checker.load_inputs(ROOT)
    identity_cases = [
        case for case in cases if case["normalizationRuleId"] == "identity"
    ]
    assert len(identity_cases) == 25
    assert all(case["raw"] == case["normalized"] for case in identity_cases)
    assert checker.check_cases(identity_cases, rules) == 25


def test_new_rule_id_with_existing_transform_is_followed() -> None:
    """既知の変換種別ならruleIdを増やしても実装追加を要しない。"""
    schema = _asset("state_transition_contract_schema_v1.json")
    rule = copy.deepcopy(schema["x-pitchlog-stage1-normalization"]["ruleCatalog"][1])
    rule["ruleId"] = "display-alias"
    schema["x-pitchlog-stage1-normalization"]["ruleCatalog"].append(rule)
    schema["$defs"]["normalizationRuleId"]["enum"].append("display-alias")
    rules = _rules_for_schema(schema)
    case = next(
        item for item in checker.load_inputs(ROOT)[0]
        if item["normalizationRuleId"] == "result-display-name-to-id"
    )
    changed = copy.deepcopy(case)
    changed["normalizationRuleId"] = "display-alias"
    assert checker.check_cases([changed], rules) == 1
