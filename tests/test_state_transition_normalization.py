"""状況判定ケースの宣言規則適用とidentity変異を検証する。"""

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
    """現行96件すべてで宣言規則の適用結果がnormalizedと一致する。"""
    assert checker.check_repository(ROOT) == 96


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
