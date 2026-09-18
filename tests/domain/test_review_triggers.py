"""design.md §12-1・§12-3 の見直しトリガー評価枠を検査する。"""

from __future__ import annotations

import copy
import json
import re
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "backend/domain/review-triggers.json"
CONDITIONS_PATH = ROOT / "backend/domain/machine-conditions.json"
STEPS_PATH = ROOT / "docs/features/domain-calc-dsl/steps.json"

TOP_LEVEL_KEYS = {
    "version",
    "authority",
    "poName",
    "evaluationStepDerivation",
    "triggers",
}
DERIVATION_KEYS = {"source", "selector", "marker", "allStepsTriggerId"}
TRIGGER_KEYS = {
    "id",
    "description",
    "evaluationSteps",
    "evaluationDeadline",
    "evaluationMethod",
    "judge",
    "evidenceLocation",
    "firingCondition",
    "evaluation",
}
METHOD_KEYS = {"conditionTypeIds", "manual", "procedure"}
JUDGE_TYPES = {"機械", "PO"}
MANUAL_MARKER = "[手動]"
TRIGGER_MARKER_PATTERN = re.compile(
    r"トリガー (?P<ids>[1-9]\d*(?:・[1-9]\d*)*) を評価"
)


@pytest.fixture(scope="module")
def registry() -> dict[str, Any]:
    """見直しトリガーの評価枠を読み込む。"""
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def conditions() -> dict[str, Any]:
    """機械条件の 12 型を読み込む。"""
    return json.loads(CONDITIONS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def steps_source() -> dict[str, Any]:
    """全ステップの単一定義を読み込む。"""
    return json.loads(STEPS_PATH.read_text(encoding="utf-8"))


def _assert_complete_trigger_population(asset: dict[str, Any]) -> None:
    """1 から 16 のトリガー枠が一度ずつ存在することを検査する。"""
    assert set(asset) == TOP_LEVEL_KEYS
    assert asset["version"] == 1
    assert asset["authority"] == "design.md §12-1・§12-3"
    assert asset["poName"] == "山田正輝"
    assert set(asset["evaluationStepDerivation"]) == DERIVATION_KEYS
    assert asset["evaluationStepDerivation"] == {
        "source": "docs/features/domain-calc-dsl/steps.json",
        "selector": "steps[].title",
        "marker": "トリガー <id> を評価",
        "allStepsTriggerId": 16,
    }

    expected_ids = set(range(1, 17))
    actual_ids = [trigger.get("id") for trigger in asset["triggers"]]
    assert len(asset["triggers"]) == 16, f"トリガー数が 16 件ではない: {len(actual_ids)}"
    missing = expected_ids - set(actual_ids)
    unexpected = set(actual_ids) - expected_ids
    assert not missing and not unexpected, (
        f"トリガー ID の集合差: 欠落={sorted(missing)!r}, 未知={sorted(unexpected)!r}"
    )
    duplicate_ids = {trigger_id for trigger_id in actual_ids if actual_ids.count(trigger_id) > 1}
    assert not duplicate_ids, f"重複したトリガー ID: {sorted(duplicate_ids)!r}"

    for trigger in asset["triggers"]:
        trigger_id = trigger["id"]
        assert set(trigger) == TRIGGER_KEYS, f"トリガー {trigger_id} のキー集合が不正"
        assert isinstance(trigger["description"], str) and trigger["description"]
        assert isinstance(trigger["firingCondition"], str) and trigger["firingCondition"]
        assert set(trigger["evaluationMethod"]) == METHOD_KEYS
        assert trigger["evaluationSteps"]
        assert trigger["evaluationSteps"] == sorted(set(trigger["evaluationSteps"]))
        assert all(
            isinstance(step_id, int) and not isinstance(step_id, bool)
            for step_id in trigger["evaluationSteps"]
        )


def _assert_methods_are_declared(asset: dict[str, Any], condition_asset: dict[str, Any]) -> None:
    """`evaluationMethod` が 12 型の ID または手動判定を指すことを検査する。"""
    declared_ids = {condition["id"] for condition in condition_asset["conditionTypes"]}
    assert len(condition_asset["conditionTypes"]) == 12
    assert len(declared_ids) == 12

    for trigger in asset["triggers"]:
        method = trigger["evaluationMethod"]
        condition_ids = method["conditionTypeIds"]
        assert isinstance(condition_ids, list)
        assert len(condition_ids) == len(set(condition_ids))
        unknown = set(condition_ids) - declared_ids
        assert not unknown, (
            f"トリガー {trigger['id']} の未知な evaluationMethod: {sorted(unknown)!r}"
        )
        assert method["manual"] in {None, MANUAL_MARKER}
        assert condition_ids or method["manual"] == MANUAL_MARKER
        assert method["procedure"] is None or (
            isinstance(method["procedure"], str) and method["procedure"]
        )


def _assert_judges_are_valid(asset: dict[str, Any]) -> None:
    """判定者が機械または氏名を固定した PO であることを検査する。"""
    assert asset["poName"] == "山田正輝"
    for trigger in asset["triggers"]:
        judges = trigger["judge"]
        assert isinstance(judges, list) and judges
        assert len(judges) == len(set(judges))
        unknown = set(judges) - JUDGE_TYPES
        assert not unknown, f"トリガー {trigger['id']} の未知な判定者: {sorted(unknown)!r}"
        if trigger["evaluationMethod"]["manual"] == MANUAL_MARKER:
            assert "PO" in judges, f"トリガー {trigger['id']} の手動判定者が PO でない"


def _assert_evidence_locations_are_declared(asset: dict[str, Any]) -> None:
    """証拠資産のリポジトリ相対パスが宣言されていることを検査する。"""
    for trigger in asset["triggers"]:
        location = trigger["evidenceLocation"]
        assert isinstance(location, str) and location
        path = PurePosixPath(location)
        assert not path.is_absolute()
        assert ".." not in path.parts


def _derive_evaluation_steps(
    source: dict[str, Any], all_steps_trigger_id: int
) -> dict[int, list[int]]:
    """`steps.json` の title からトリガーと評価ステップの対応を導出する。

    Args:
        source: `steps.json` の全体。
        all_steps_trigger_id: 全ステップで評価する例外トリガー ID。

    Returns:
        トリガー ID から評価ステップ ID の昇順リストへの対応。
    """
    derived: defaultdict[int, set[int]] = defaultdict(set)
    step_ids = {step["id"] for step in source["steps"]}
    for step in source["steps"]:
        for match in TRIGGER_MARKER_PATTERN.finditer(step["title"]):
            for trigger_id in match.group("ids").split("・"):
                derived[int(trigger_id)].add(step["id"])

    derived[all_steps_trigger_id] = step_ids
    return {trigger_id: sorted(ids) for trigger_id, ids in derived.items()}


def _assert_evaluation_steps_exist(asset: dict[str, Any], source: dict[str, Any]) -> None:
    """評価ステップが `steps.json` の実在する ID のみを指すことを検査する。"""
    existing_ids = {step["id"] for step in source["steps"]}
    for trigger in asset["triggers"]:
        unknown = set(trigger["evaluationSteps"]) - existing_ids
        assert not unknown, (
            f"トリガー {trigger['id']} の実在しない評価ステップ: {sorted(unknown)!r}"
        )


def _assert_evaluation_steps_match_derivation(
    asset: dict[str, Any], source: dict[str, Any]
) -> None:
    """タイトルから独立導出した対応と資産を集合差で比較する。"""
    exception_id = asset["evaluationStepDerivation"]["allStepsTriggerId"]
    expected = _derive_evaluation_steps(source, exception_id)
    actual = {trigger["id"]: trigger["evaluationSteps"] for trigger in asset["triggers"]}

    expected_pairs = {
        (trigger_id, step_id)
        for trigger_id, step_ids in expected.items()
        for step_id in step_ids
    }
    actual_pairs = {
        (trigger_id, step_id)
        for trigger_id, step_ids in actual.items()
        for step_id in step_ids
    }
    missing = expected_pairs - actual_pairs
    unexpected = actual_pairs - expected_pairs
    assert not missing and not unexpected, (
        f"評価ステップの集合差: 欠落={sorted(missing)!r}, 未知={sorted(unexpected)!r}"
    )
    assert set(expected) == set(range(1, 17))
    assert actual[exception_id] == sorted(step["id"] for step in source["steps"])
    exception = next(trigger for trigger in asset["triggers"] if trigger["id"] == exception_id)
    assert exception["evaluationDeadline"] == max(actual[exception_id])


def _assert_deadlines_match_last_evaluation_step(asset: dict[str, Any]) -> None:
    """例外以外の期限が最後の評価ステップと一致することを検査する。"""
    exception_id = asset["evaluationStepDerivation"]["allStepsTriggerId"]
    for trigger in asset["triggers"]:
        if trigger["id"] == exception_id:
            continue
        expected = max(trigger["evaluationSteps"])
        assert trigger["evaluationDeadline"] == expected, (
            f"トリガー {trigger['id']} の期限: "
            f"実測={trigger['evaluationDeadline']}, 期待={expected}"
        )


def _assert_evaluation_records_are_valid(asset: dict[str, Any]) -> None:
    """評価値が未評価または閉じた発火レコードであることを検査する。"""
    for trigger in asset["triggers"]:
        evaluation = trigger["evaluation"]
        if evaluation is None:
            continue
        assert isinstance(evaluation, dict), (
            f"トリガー {trigger['id']} の evaluation が object でない"
        )
        assert set(evaluation) == {"fired"}, (
            f"トリガー {trigger['id']} の evaluation のキー集合が不正"
        )
        assert isinstance(evaluation["fired"], bool), (
            f"トリガー {trigger['id']} の fired が boolean でない"
        )
        assert isinstance(trigger["evidenceLocation"], str) and trigger[
            "evidenceLocation"
        ], f"トリガー {trigger['id']} の証拠資産の置き場が空"


def _with_all_evaluations_empty(asset: dict[str, Any]) -> dict[str, Any]:
    """全トリガーを未評価にした検査用の写しを返す。"""
    unevaluated = copy.deepcopy(asset)
    for trigger in unevaluated["triggers"]:
        trigger["evaluation"] = None
    return unevaluated


def _assert_all_evaluations_are_empty(asset: dict[str, Any]) -> None:
    """検査用の写しで全トリガーが未評価であることを検査する。"""
    nonempty = {
        trigger["id"] for trigger in asset["triggers"] if trigger["evaluation"] is not None
    }
    assert not nonempty, f"未評価でないトリガー: {sorted(nonempty)!r}"


def _validate_unevaluated_registry(
    asset: dict[str, Any], condition_asset: dict[str, Any], source: dict[str, Any]
) -> None:
    """未評価の 16 枠に必要な検査をすべて適用する。"""
    _assert_complete_trigger_population(asset)
    _assert_methods_are_declared(asset, condition_asset)
    _assert_judges_are_valid(asset)
    _assert_evidence_locations_are_declared(asset)
    _assert_evaluation_steps_exist(asset, source)
    _assert_evaluation_steps_match_derivation(asset, source)
    _assert_deadlines_match_last_evaluation_step(asset)
    _assert_evaluation_records_are_valid(asset)
    _assert_all_evaluations_are_empty(asset)


def test_registry_has_exactly_sixteen_trigger_frames(registry: dict[str, Any]) -> None:
    _assert_complete_trigger_population(registry)


def test_evaluation_methods_use_declared_machine_condition_types(
    registry: dict[str, Any], conditions: dict[str, Any]
) -> None:
    _assert_methods_are_declared(registry, conditions)


def test_judges_are_machine_or_named_po(registry: dict[str, Any]) -> None:
    _assert_judges_are_valid(registry)
    po_ids = {
        trigger["id"] for trigger in registry["triggers"] if "PO" in trigger["judge"]
    }
    assert po_ids == {1, 2, 5, 7, 8, 10, 11, 12, 15}
    assert len(po_ids) == 9


def test_evidence_locations_are_declared_without_requiring_existence(
    registry: dict[str, Any],
) -> None:
    _assert_evidence_locations_are_declared(registry)
    future_asset = copy.deepcopy(registry)
    for trigger in future_asset["triggers"]:
        trigger["evidenceLocation"] = f"future/evidence/trigger-{trigger['id']}.json"
        assert not (ROOT / trigger["evidenceLocation"]).exists()
    _assert_evidence_locations_are_declared(future_asset)


def test_evaluation_steps_exist_and_match_title_derivation(
    registry: dict[str, Any], steps_source: dict[str, Any]
) -> None:
    _assert_evaluation_steps_exist(registry, steps_source)
    _assert_evaluation_steps_match_derivation(registry, steps_source)


def test_evaluation_records_have_closed_shape_and_evidence_location(
    registry: dict[str, Any],
) -> None:
    _assert_evaluation_records_are_valid(registry)


def test_all_trigger_evaluations_may_be_empty(registry: dict[str, Any]) -> None:
    unevaluated = _with_all_evaluations_empty(registry)
    _assert_evaluation_records_are_valid(unevaluated)
    _assert_all_evaluations_are_empty(unevaluated)


def test_deadlines_match_last_evaluation_steps(registry: dict[str, Any]) -> None:
    _assert_deadlines_match_last_evaluation_step(registry)


def test_all_sixteen_unevaluated_frames_are_accepted(
    registry: dict[str, Any], conditions: dict[str, Any], steps_source: dict[str, Any]
) -> None:
    unevaluated = _with_all_evaluations_empty(registry)
    _validate_unevaluated_registry(unevaluated, conditions, steps_source)


def test_missing_trigger_is_rejected(registry: dict[str, Any]) -> None:
    mutated = copy.deepcopy(registry)
    mutated["triggers"] = [trigger for trigger in mutated["triggers"] if trigger["id"] != 16]

    with pytest.raises(AssertionError, match="16 件"):
        _assert_complete_trigger_population(mutated)


def test_unknown_evaluation_method_is_rejected(
    registry: dict[str, Any], conditions: dict[str, Any]
) -> None:
    mutated = copy.deepcopy(registry)
    mutated["triggers"][0]["evaluationMethod"]["conditionTypeIds"] = ["unknown_method"]

    with pytest.raises(AssertionError, match="unknown_method"):
        _assert_methods_are_declared(mutated, conditions)


def test_unknown_judge_is_rejected(registry: dict[str, Any]) -> None:
    mutated = copy.deepcopy(registry)
    mutated["triggers"][0]["judge"] = ["第三者"]

    with pytest.raises(AssertionError, match="第三者"):
        _assert_judges_are_valid(mutated)


def test_nonexistent_evaluation_step_is_rejected(
    registry: dict[str, Any], steps_source: dict[str, Any]
) -> None:
    mutated = copy.deepcopy(registry)
    mutated["triggers"][0]["evaluationSteps"].append(57)

    with pytest.raises(AssertionError, match="57"):
        _assert_evaluation_steps_exist(mutated, steps_source)


def test_deadline_before_last_evaluation_step_is_rejected(registry: dict[str, Any]) -> None:
    mutated = copy.deepcopy(registry)
    trigger_five = next(trigger for trigger in mutated["triggers"] if trigger["id"] == 5)
    trigger_five["evaluationDeadline"] = 47

    with pytest.raises(AssertionError, match="トリガー 5"):
        _assert_deadlines_match_last_evaluation_step(mutated)


def test_non_boolean_fired_value_is_rejected(registry: dict[str, Any]) -> None:
    mutated = copy.deepcopy(registry)
    mutated["triggers"][0]["evaluation"] = {"fired": "yes"}

    with pytest.raises(AssertionError, match="boolean"):
        _assert_evaluation_records_are_valid(mutated)


def test_extra_evaluation_key_is_rejected(registry: dict[str, Any]) -> None:
    mutated = copy.deepcopy(registry)
    mutated["triggers"][0]["evaluation"] = {"fired": False, "note": "余分なキー"}

    with pytest.raises(AssertionError, match="キー集合"):
        _assert_evaluation_records_are_valid(mutated)
