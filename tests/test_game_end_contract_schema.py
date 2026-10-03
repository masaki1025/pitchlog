"""終了判定契約schemaの構造とF-1規則スナップショットを検証する。"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_input_axes_descriptor.py"
FREEZE_CHECKER_PATH = REPOSITORY_ROOT / "scripts/state_transition_freeze.py"
SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "contracts/state-transition/game_end_contract_schema_v1.json"
)
CONTRACT_PATH = (
    REPOSITORY_ROOT / "contracts/state-transition/game_end_contract_v1.json"
)
DESCRIPTOR_PATH = (
    REPOSITORY_ROOT / "contracts/state-transition/input_axes_descriptor_v1.json"
)


def _load_module(name: str, path: Path) -> Any:
    """テスト対象をsys.path変更なしで読み込む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_module("state_transition_freeze", FREEZE_CHECKER_PATH)
schema_checker = _load_module(
    "game_end_contract_descriptor_checker", DESCRIPTOR_CHECKER_PATH
)


def _load_object(path: Path) -> dict[str, Any]:
    """JSON objectを読み込む。

    Args:
        path: 読み込むJSONファイル。

    Returns:
        読み込んだJSON object。
    """
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _schema() -> dict[str, Any]:
    """終了判定契約schemaを返す。"""
    return _load_object(SCHEMA_PATH)


def _descriptor() -> dict[str, Any]:
    """入力軸descriptorを返す。"""
    return _load_object(DESCRIPTOR_PATH)


def _repository_contract() -> dict[str, Any]:
    """実資産の終了判定契約を返す。"""
    return _load_object(CONTRACT_PATH)


def _decision_leaves(predicate: Mapping[str, Any]) -> list[dict[str, Any]]:
    """終了判定述語の比較葉を列挙する。

    Args:
        predicate: 閉じた述語AST。

    Returns:
        比較葉の一覧。
    """
    if predicate["op"] == "eq":
        assert isinstance(predicate, dict)
        return [predicate]
    return [
        leaf
        for argument in predicate["args"]
        for leaf in _decision_leaves(argument)
    ]


def _validate_decision_references(contract: Mapping[str, Any]) -> None:
    """schemaの参照宣言に従って分岐と入力軸を検証する。

    Args:
        contract: 検証する終了判定契約。
    """
    schema = _schema()
    _validate_contract(contract)
    policy = schema["x-pitchlog-decision-row-references"]
    register = _load_object(REPOSITORY_ROOT / policy["branchRegisterPath"])
    descriptor = _load_object(REPOSITORY_ROOT / policy["axisDescriptorPath"])
    branches = {row["branchId"]: row for row in register["branches"]}
    axes = {
        axis["axisId"]: axis
        for collection in ("gameEndAxes", "stateTransitionAxes")
        for axis in descriptor[collection]
    }
    allowed_axes = set(policy["allowedAxisIds"])
    assert {axis["axisId"] for axis in descriptor["gameEndAxes"]} <= allowed_axes
    assert allowed_axes <= set(axes)
    rows = contract["decisionRows"]
    branch_ids = [row["branchId"] for row in rows]
    assert len(branch_ids) == len(set(branch_ids))
    classification_overrides = policy["branchClassificationOverrides"]
    assert set(classification_overrides) <= set(branch_ids)
    outcome_enum = set(schema["$defs"]["gameEndDecision"]["properties"]["outcome"]["enum"])
    assert set(policy["outcomeSourceClauseIds"]) == outcome_enum
    assert all(
        sources and all(source.startswith("req:") for source in sources)
        for sources in policy["outcomeSourceClauseIds"].values()
    )
    assert set(policy["outcomeByBranchId"].values()) <= outcome_enum
    for row in rows:
        branch = branches.get(row["branchId"])
        assert branch is not None
        classification = classification_overrides.get(row["branchId"], {})
        assert branch["branchKind"] == classification.get(
            "branchKind", policy["requiredBranchKind"]
        )
        assert branch["coverageKind"] == classification.get(
            "coverageKind", policy["requiredCoverageKind"]
        )
        assert set(row["sourceClauseIds"]) == set(branch["sourceClauseIds"])
        assert row["decision"]["outcome"] == policy["outcomeByBranchId"][
            row["branchId"]
        ]
        for leaf in _decision_leaves(row["precondition"]):
            axis_id = leaf["axisId"]
            assert axis_id in allowed_axes
            axis = axes[axis_id]
            value_field = policy["valueFieldsByClassification"][axis["classification"]]
            assert any(
                type(leaf["value"]) is type(value) and leaf["value"] == value
                for value in axis[value_field]
            )
    assert set(branch_ids) == set(policy["implementedBranchIds"])
    assert set(policy["outcomeByBranchId"]) == set(branch_ids)
    assert set(register["gameEndOutcomeBranches"].values()) <= set(branch_ids)


def _valid_rule_snapshot() -> dict[str, Any]:
    """付録F-1に適合する代表的な規則スナップショットを返す。"""
    return {
        "regulationInnings": 9,
        "coldConditions": [
            {"pointDifference": 10, "startInning": 5},
            {"pointDifference": 7, "startInning": 7},
        ],
        "extensionLimit": 12,
        "tiebreak": {
            "startInning": 10,
            "runnerPlacement": "無死一・二塁",
            "leadoffRule": "継続打順",
        },
        "dh": True,
    }


def _minimal_contract() -> dict[str, Any]:
    """D-6の終了判定契約要素を持つ最小契約を返す。"""
    descriptor = _descriptor()
    return {
        "schemaVersion": 1,
        "version": "game_end_contract_v1",
        "calculation": "game-end",
        "inputAxesDescriptor": {
            "descriptorId": descriptor["descriptorId"],
            "version": descriptor["version"],
            "digest": descriptor["digest"],
        },
        "decisionRows": [],
        "requiredSet": {},
        "cases": [],
        "validationErrors": [],
    }


def _validate_contract(contract: Mapping[str, Any]) -> None:
    """終了判定契約をschemaで検証する。"""
    schema = _schema()
    schema_checker._validate_instance(contract, schema, schema, "$")


def _validate_rule_snapshot(snapshot: Mapping[str, Any]) -> None:
    """規則スナップショットをF-1の型で検証する。"""
    schema = _schema()
    definition = schema["$defs"]["ruleSnapshot"]
    schema_checker._validate_instance(snapshot, definition, schema, "$.ruleSnapshot")


def _projection_annotations(
    value: object,
    annotation: str,
) -> dict[str, Mapping[str, Any]]:
    """schema内の射影annotationをtarget IDで索引化する。

    Args:
        value: 探索対象のJSON値。
        annotation: target IDを保持するannotation名。

    Returns:
        target IDから当該schema objectへの写像。
    """
    found: dict[str, Mapping[str, Any]] = {}
    if isinstance(value, dict):
        target_id = value.get(annotation)
        if isinstance(target_id, str):
            assert target_id not in found
            found[target_id] = value
        for child in value.values():
            for child_id, child_schema in _projection_annotations(
                child, annotation
            ).items():
                assert child_id not in found
                found[child_id] = child_schema
    elif isinstance(value, list):
        for child in value:
            for child_id, child_schema in _projection_annotations(
                child, annotation
            ).items():
                assert child_id not in found
                found[child_id] = child_schema
    return found


def test_contract_has_d6_game_end_collections_and_descriptor_binding() -> None:
    """D-6の終了判定契約要素とdescriptor identity拘束を保持する。"""
    schema = _schema()
    descriptor = _descriptor()
    binding = schema["$defs"]["inputAxesDescriptorBinding"]["properties"]

    assert set(schema["required"]) == {
        "schemaVersion",
        "version",
        "calculation",
        "inputAxesDescriptor",
        "decisionRows",
        "requiredSet",
        "cases",
        "validationErrors",
    }
    assert schema["properties"]["decisionRows"][
        "x-pitchlog-normative-row-layer"
    ] is True
    assert binding["descriptorId"]["const"] == descriptor["descriptorId"]
    assert binding["version"]["const"] == descriptor["version"]
    assert binding["digest"]["const"] == descriptor["digest"]
    _validate_contract(_minimal_contract())


def test_repository_decision_rows_are_closed_and_references_resolve() -> None:
    """実資産の規範行を閉じた型・分岐・軸の参照と突合する。"""
    schema = _schema()
    row_schema = schema["$defs"]["decisionRow"]
    assert set(row_schema["required"]) == set(row_schema["properties"])
    assert row_schema["additionalProperties"] is False
    assert schema["x-pitchlog-decision-row-references"]["evaluationPoint"]
    _validate_decision_references(_repository_contract())


@pytest.mark.parametrize("mutation", ["unknown-column", "missing-column", "invalid-outcome"])
def test_decision_row_shape_mutations_are_red(mutation: str) -> None:
    """未知列・必須列欠落・enum外の結果を拒否する。"""
    contract = deepcopy(_repository_contract())
    row = contract["decisionRows"][0]
    if mutation == "unknown-column":
        row["unexpected"] = True
    elif mutation == "missing-column":
        del row["remarks"]
    else:
        row["decision"]["outcome"] = "unknown-outcome"
    with pytest.raises(schema_checker.DescriptorCheckError):
        _validate_decision_references(contract)


def test_nonexistent_decision_branch_is_red() -> None:
    """実在しない分岐IDをregister突合で拒否する。"""
    contract = deepcopy(_repository_contract())
    contract["decisionRows"][0]["branchId"] = "GAME-END-UNKNOWN"
    with pytest.raises(AssertionError):
        _validate_decision_references(contract)


def test_normative_case_branch_cannot_be_used_as_decision_row() -> None:
    """宣言のない中間判定分岐を終了結果行へ誤登録させない。"""
    contract = deepcopy(_repository_contract())
    contract["decisionRows"][0]["branchId"] = "COLD-01"
    contract["decisionRows"][0]["sourceClauseIds"] = ["req:F-1"]
    with pytest.raises(AssertionError):
        _validate_decision_references(contract)


def test_cold_outcome_and_single_tier_row_are_clause_bound() -> None:
    """コールドの結果語彙と単一成立段の行を条文宣言へ結びつける。"""
    schema = _schema()
    policy = schema["x-pitchlog-decision-row-references"]
    rows = _repository_contract()["decisionRows"]
    cold_row = next(row for row in rows if row["branchId"] == "COLD-08")

    assert policy["outcomeByBranchId"]["COLD-08"] == "cold-end"
    assert "req:F-1" in policy["outcomeSourceClauseIds"]["cold-end"]
    assert "req:FR-005" in policy["outcomeSourceClauseIds"]["walk-off"]
    assert cold_row["decision"] == {
        "outcome": "cold-end",
        "endConditionDetected": True,
        "lockFurtherPlayInput": True,
        "promptEndDeclaration": True,
        "automaticallyEndsGame": False,
    }
    assert {leaf["axisId"]: leaf["value"] for leaf in _decision_leaves(cold_row["precondition"])}[
        "gameEnd.coldConditions"
    ] == "tier-count:1"
    _validate_decision_references(_repository_contract())


@pytest.mark.parametrize("mutation", ["wrong-outcome", "unknown-tier"])
def test_cold_row_mutations_are_red(mutation: str) -> None:
    """コールド行の結果取り違えとdescriptor外の段数を拒否する。"""
    contract = deepcopy(_repository_contract())
    cold_row = next(row for row in contract["decisionRows"] if row["branchId"] == "COLD-08")
    if mutation == "wrong-outcome":
        cold_row["decision"]["outcome"] = "normal-end"
    else:
        leaf = next(
            leaf
            for leaf in _decision_leaves(cold_row["precondition"])
            if leaf["axisId"] == "gameEnd.coldConditions"
        )
        leaf["value"] = "tier-count:2"
    with pytest.raises(AssertionError):
        _validate_decision_references(contract)


def test_decision_outcome_swapped_between_existing_branches_is_red() -> None:
    """実在する別の結果への取り違えもschema宣言との突合で拒否する。"""
    contract = deepcopy(_repository_contract())
    contract["decisionRows"][0]["decision"]["outcome"] = "limit-draw"
    with pytest.raises(AssertionError):
        _validate_decision_references(contract)


@pytest.mark.parametrize(
    ("axis_id", "value"),
    [
        ("gameEnd.extensionLimit", "finite:R-1"),
        ("gameEnd.regulationInnings", 0),
        ("event.operationKind", "per-pitch"),
    ],
)
def test_decision_precondition_outside_declared_axes_is_red(
    axis_id: str, value: object
) -> None:
    """境界値外と終了判定に許さない軸を拒否する。"""
    contract = deepcopy(_repository_contract())
    leaf = _decision_leaves(contract["decisionRows"][0]["precondition"])[0]
    leaf["axisId"] = axis_id
    leaf["value"] = value
    with pytest.raises(AssertionError):
        _validate_decision_references(contract)


def test_f1_rule_snapshot_has_exactly_five_closed_fields() -> None:
    """付録F-1の5フィールドをrequiredかつ閉じたobjectとして保持する。"""
    rule_snapshot = _schema()["$defs"]["ruleSnapshot"]

    assert set(rule_snapshot["required"]) == {
        "regulationInnings",
        "coldConditions",
        "extensionLimit",
        "tiebreak",
        "dh",
    }
    assert set(rule_snapshot["properties"]) == set(rule_snapshot["required"])
    assert rule_snapshot["additionalProperties"] is False
    _validate_rule_snapshot(_valid_rule_snapshot())


def test_rule_snapshot_allows_explicit_none_and_empty_cold_conditions() -> None:
    """F-1の「なし」をnull、コールドなしを空配列として受理する。"""
    snapshot = _valid_rule_snapshot()
    snapshot["coldConditions"] = []
    snapshot["extensionLimit"] = None
    snapshot["tiebreak"] = None

    _validate_rule_snapshot(snapshot)


def test_all_descriptor_game_end_targets_are_projected_exactly_once() -> None:
    """gameEndAxes4件を境界注釈とともにexact-set射影する。"""
    schema = _schema()
    descriptor = _descriptor()
    rule_snapshot = schema["$defs"]["ruleSnapshot"]
    projected = _projection_annotations(rule_snapshot, "x-pitchlog-axis-id")
    expected = {axis["axisId"]: axis for axis in descriptor["gameEndAxes"]}

    assert set(projected) == set(expected)
    for axis_id, axis in expected.items():
        target = projected[axis_id]
        assert target["x-pitchlog-axis-classification"] == axis["classification"]
        assert target["x-pitchlog-coverage-bounds"] == axis["coverageBounds"]
        assert target["x-pitchlog-boundary-values"] == axis["boundaryValues"]
        assert target["x-pitchlog-invalid-boundary-values"] == axis[
            "invalidBoundaryValues"
        ]


def test_all_non_coverage_fields_remain_required_by_projection() -> None:
    """終了判定に使わない3葉もdescriptorどおりschemaへ保持する。"""
    schema = _schema()
    descriptor = _descriptor()
    projected = _projection_annotations(schema, "x-pitchlog-non-coverage-field")
    expected = {
        field["fieldId"]: field for field in descriptor["nonCoverageFields"]
    }

    assert set(projected) == set(expected)
    for field_id, field in expected.items():
        target = projected[field_id]
        assert target["x-pitchlog-non-coverage-reason"] == field["reason"]
        assert target["x-pitchlog-schema-retention"] == field["schemaRetention"]
        assert field["schemaRetention"] == "required-by-projection"


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("regulationInnings", 0),
        (
            "coldConditions",
            [{"pointDifference": 0, "startInning": 5}],
        ),
        ("extensionLimit", "なし"),
        (
            "tiebreak",
            {
                "startInning": 10,
                "runnerPlacement": "無死一・二塁",
                "leadoffRule": "",
            },
        ),
        ("dh", "あり"),
    ],
)
def test_out_of_schema_value_is_red(field: str, invalid_value: object) -> None:
    """F-1の各フィールドでschema外の値を拒否する。"""
    snapshot = _valid_rule_snapshot()
    snapshot[field] = invalid_value

    with pytest.raises(schema_checker.DescriptorCheckError):
        _validate_rule_snapshot(snapshot)


@pytest.mark.parametrize(
    "field",
    [
        "regulationInnings",
        "coldConditions",
        "extensionLimit",
        "tiebreak",
        "dh",
    ],
)
def test_missing_f1_field_is_red(field: str) -> None:
    """F-1の各requiredフィールドの欠落を拒否する。"""
    snapshot = _valid_rule_snapshot()
    del snapshot[field]

    with pytest.raises(
        schema_checker.DescriptorCheckError,
        match=rf"必須キー不足: .*{field}",
    ):
        _validate_rule_snapshot(snapshot)


def test_unknown_rule_snapshot_field_is_red() -> None:
    """F-1に無い6番目の規則フィールドを拒否する。"""
    snapshot = _valid_rule_snapshot()
    snapshot["mercyRuleLabel"] = "独自規則"

    with pytest.raises(
        schema_checker.DescriptorCheckError,
        match="未知キー: .*mercyRuleLabel",
    ):
        _validate_rule_snapshot(snapshot)


def test_non_coverage_tiebreak_leaf_is_still_required() -> None:
    """coverage対象外でも走者配置と先頭打者規則を省略させない。"""
    snapshot = _valid_rule_snapshot()
    del snapshot["tiebreak"]["runnerPlacement"]

    with pytest.raises(
        schema_checker.DescriptorCheckError,
        match="oneOfに一意に一致しない",
    ):
        _validate_rule_snapshot(snapshot)
