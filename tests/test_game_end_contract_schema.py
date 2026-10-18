"""終了判定契約schemaの構造とF-1規則スナップショットを検証する。"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path, PurePosixPath
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


def _manual_fixture_assets() -> tuple[dict[str, Any], dict[str, Any]]:
    """終了判定の手作業fixtureとschemaを返す。"""
    schema = _load_object(
        REPOSITORY_ROOT
        / "contracts/state-transition/game_end_manual_fixture_schema_v1.json"
    )
    path = schema["x-pitchlog-manual-fixture-policy"]["fixturePath"]
    return _load_object(REPOSITORY_ROOT / path), schema


def _fixture_predicate_holds(
    predicate: Mapping[str, Any], coordinate: Mapping[str, Any]
) -> bool:
    """規範行の述語がfixtureの入力座標に一致するかを返す。

    Args:
        predicate: 規範行のPredicate AST。
        coordinate: 完全な境界入力座標。

    Returns:
        述語が成立すればTrue。
    """
    operator = predicate["op"]
    if operator == "eq":
        # 手作業fixtureは凍結時の軸射影で、後から固定した未開始の裏は派生caseで照合する。
        if predicate["axisId"] in {
            "gameEnd.satisfiedColdTierCount", "state.outs", "state.runners",
            "state.count.strikes", "state.count.balls",
            "event.operationPayload", "event.perPitch.pitchEventKind",
            "event.perPitch.runnerEventPayload",
            "event.perPitch.runnerAdvanceOverridesByRunner",
            "event.perPitch.thirdOutTimingByRunner",
            "event.perPitch.interferenceRuling",
            "event.perPitch.officialScoringPayload",
            "event.perPitch.rbi.doublePlayRelayError",
            "event.perPitch.rbi.runnerContinuityByRunner",
            "event.perPitch.rbi.wouldScoreWithoutErrorByRunner",
        }:
            return True
        actual = coordinate[predicate["axisId"]]
        expected = predicate["value"]
        return type(actual) is type(expected) and actual == expected
    if operator == "and":
        return all(_fixture_predicate_holds(arg, coordinate) for arg in predicate["args"])
    if operator == "or":
        return any(_fixture_predicate_holds(arg, coordinate) for arg in predicate["args"])
    assert operator == "not"
    return not _fixture_predicate_holds(predicate["args"][0], coordinate)


def _validate_manual_fixtures(
    document: dict[str, Any], schema: dict[str, Any]
) -> None:
    """終了判定fixtureの型・典拠・入力と出力全体を検査する。

    Args:
        document: fixture文書。
        schema: fixtureのschemaと宣言。
    """
    schema_checker._validate_instance(document, schema, schema, "$")
    policy = schema["x-pitchlog-manual-fixture-policy"]
    register = _load_object(REPOSITORY_ROOT / policy["branchRegisterPath"])
    contract = _load_object(REPOSITORY_ROOT / policy["normativeContractPath"])
    contract_schema = _load_object(REPOSITORY_ROOT / policy["normativeSchemaPath"])
    descriptor = _load_object(REPOSITORY_ROOT / policy["axisDescriptorPath"])
    partition_schema = _load_object(REPOSITORY_ROOT / policy["branchPartitionPolicyPath"])
    clause_ids = schema_checker.load_clause_ids_from_paths(
        REPOSITORY_ROOT, (PurePosixPath(policy["requirementsPath"]),)
    )
    known_sources = {f"req:{clause_id}" for clause_id in clause_ids}
    game_end_sources = set(
        partition_schema["x-pitchlog-manual-fixture-policy"]
        ["sourceClausePartition"]["gameEndSourceClauseIds"]
    )
    situation_overrides = set(
        partition_schema["x-pitchlog-manual-fixture-policy"]
        ["sourceClausePartition"]["situationBranchOverrides"]
    )
    branches = {branch["branchId"]: branch for branch in register["branches"]}
    game_end_ids = {
        branch_id
        for branch_id, branch in branches.items()
        if set(branch["sourceClauseIds"]) & game_end_sources
        and branch_id not in situation_overrides
    }
    deferred = policy["deferredBranches"]
    assert all(isinstance(reason, str) and reason for reason in deferred.values())
    cases = [fixture["case"] for fixture in document["fixtures"]]
    case_ids = [case["caseId"] for case in cases]
    branch_ids = [case["branchId"] for case in cases]
    assert len(case_ids) == len(set(case_ids))
    assert len(branch_ids) == len(set(branch_ids))
    assert set(branch_ids).isdisjoint(deferred)
    assert set(branch_ids) | set(deferred) == game_end_ids
    assert set(policy["comparisonProjection"]) == set(
        schema["$defs"]["completeCase"]["required"]
    )
    allowed_axes = set(contract_schema["x-pitchlog-decision-row-references"]["allowedAxisIds"])
    assert set(schema["$defs"]["inputCoordinate"]["required"]) <= allowed_axes
    assert set(schema["$defs"]["inputCoordinate"]["properties"]) == (
        allowed_axes - {
            "gameEnd.satisfiedColdTierCount", "state.outs", "state.runners",
            "state.count.strikes", "state.count.balls",
            "event.operationPayload", "event.perPitch.pitchEventKind",
            "event.perPitch.runnerEventPayload",
            "event.perPitch.runnerAdvanceOverridesByRunner",
            "event.perPitch.thirdOutTimingByRunner",
            "event.perPitch.interferenceRuling",
            "event.perPitch.officialScoringPayload",
            "event.perPitch.rbi.doublePlayRelayError",
            "event.perPitch.rbi.runnerContinuityByRunner",
            "event.perPitch.rbi.wouldScoreWithoutErrorByRunner",
        }
    )
    assert set(schema["$defs"]["decision"]["required"]) == set(
        contract_schema["$defs"]["gameEndDecision"]["required"]
    )
    assert schema["$defs"]["decision"]["properties"] == contract_schema["$defs"][
        "gameEndDecision"
    ]["properties"]
    axes = {
        axis["axisId"]: axis
        for collection in ("gameEndAxes", "stateTransitionAxes")
        for axis in descriptor[collection]
    }
    rows = {row["branchId"]: row for row in contract["decisionRows"]}
    for fixture in document["fixtures"]:
        case = fixture["case"]
        branch = branches[case["branchId"]]
        row = rows[case["branchId"]]
        for source in fixture["provenance"]["sources"]:
            if source["sourceKind"] == "requirements":
                assert source["sourceId"] in known_sources
                assert source["sourceId"] in branch["sourceClauseIds"]
        coordinate = case["inputCoordinate"]
        for axis_id, value in coordinate.items():
            axis = axes[axis_id]
            field = "boundaryValues" if axis["classification"] == "boundary-partition" else "values"
            assert any(type(value) is type(item) and value == item for item in axis[field])
        assert _fixture_predicate_holds(row["precondition"], coordinate)
        assert case["decision"] == row["decision"]


def test_repository_game_end_manual_fixtures() -> None:
    """6件の完全な入力・出力ケースと未作成分岐の宣言を検査する。"""
    document, schema = _manual_fixture_assets()
    _validate_manual_fixtures(document, schema)
    policy = schema["x-pitchlog-manual-fixture-policy"]
    assert policy["comparisonStatus"] == (
        "complete-input-coordinate-and-complete-decision-not-yet-compared-with-expander-or-frozen"
    )
    assert "complete-case-equality-with-expanded-cases" in policy["futureMachineGuarantees"]
    assert "fixture-digest-freeze" in policy["futureMachineGuarantees"]
    assert "semantic-completeness-of-each-branch" in policy["humanControls"]


@pytest.mark.parametrize(
    "change",
    ["unknown-field", "missing-decision-field", "wrong-author", "bad-axis-value"],
)
def test_game_end_manual_fixture_schema_negatives(change: str) -> None:
    """閉じたケース形式と由来・入力値域の負例を確かめる。"""
    document, schema = _manual_fixture_assets()
    fixture = document["fixtures"][0]
    if change == "unknown-field":
        fixture["case"]["unexpected"] = True
    elif change == "missing-decision-field":
        del fixture["case"]["decision"]["automaticallyEndsGame"]
    elif change == "wrong-author":
        fixture["provenance"]["authorId"] = "human"
    else:
        fixture["case"]["inputCoordinate"]["gameEnd.regulationInnings"] = 8
    with pytest.raises((AssertionError, schema_checker.DescriptorCheckError)):
        _validate_manual_fixtures(document, schema)


@pytest.mark.parametrize("change", ["missing-branch", "bad-source", "bad-decision"])
def test_game_end_manual_fixture_reference_negatives(change: str) -> None:
    """分岐欠落・偽の典拠・出力不一致を捕まえる。"""
    document, schema = _manual_fixture_assets()
    if change == "missing-branch":
        document["fixtures"].pop(0)
    elif change == "bad-source":
        document["fixtures"][0]["provenance"]["sources"][0]["sourceId"] = (
            "req:NOT-EXISTS"
        )
    else:
        document["fixtures"][0]["case"]["decision"]["lockFurtherPlayInput"] = False
    with pytest.raises(AssertionError):
        _validate_manual_fixtures(document, schema)


@pytest.mark.parametrize("change", ["missing-walk-off", "wrong-result", "wrong-lock"])
def test_walk_off_manual_fixture_drift_is_rejected(change: str) -> None:
    """独立fixtureの欠落、プレイ種別、入力ロックのずれを拒否する。"""
    document, schema = _manual_fixture_assets()
    fixture = next(
        item for item in document["fixtures"]
        if item["case"]["branchId"] == "GAME-END-WALK-OFF"
    )
    if change == "missing-walk-off":
        document["fixtures"].remove(fixture)
    elif change == "wrong-result":
        fixture["case"]["inputCoordinate"]["event.perPitch.resultId"] = "三振"
    else:
        fixture["case"]["decision"]["lockFurtherPlayInput"] = False
    with pytest.raises(AssertionError):
        _validate_manual_fixtures(document, schema)


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
        "provenance": deepcopy(_repository_contract()["provenance"]),
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
        "provenance",
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


@pytest.mark.parametrize("mutation", ["missing", "display-string", "unknown"])
def test_x_mark_is_required_structured_enum(mutation: str) -> None:
    """X表記は表示文字列ではなく閉じた種別として全判定行に必要。"""
    schema = _schema()
    decision = schema["$defs"]["gameEndDecision"]
    assert decision["properties"]["xMark"]["enum"] == [
        "recorded-score", "x-mark", "blank"
    ]
    contract = deepcopy(_repository_contract())
    if mutation == "missing":
        del contract["decisionRows"][0]["decision"]["xMark"]
    else:
        contract["decisionRows"][0]["decision"]["xMark"] = (
            "X" if mutation == "display-string" else "unknown"
        )
    with pytest.raises(schema_checker.DescriptorCheckError):
        _validate_contract(contract)


def test_x_mark_blank_is_a_valid_structured_kind() -> None:
    """XMARK-03の空欄種別もschemaの値域に含める。"""
    contract = deepcopy(_repository_contract())
    contract["decisionRows"][0]["decision"]["xMark"] = "blank"
    _validate_contract(contract)


@pytest.mark.parametrize("missing", ["raw", "normalizationRuleId", "normalized"])
def test_game_end_case_schema_requires_normalization_triple(missing: str) -> None:
    """終了判定caseの正規化3点がどれか欠けたらschemaで拒否する。"""
    schema = _schema()
    assert schema["properties"]["cases"]["items"]["$ref"] == "#/$defs/normalizedCase"
    contract = _repository_contract()
    _validate_contract(contract)
    del contract["cases"][0][missing]
    with pytest.raises(schema_checker.DescriptorCheckError, match="必須キー不足"):
        _validate_contract(contract)


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
        "xMark": "x-mark",
    }
    assert {leaf["axisId"]: leaf["value"] for leaf in _decision_leaves(cold_row["precondition"])}[
        "gameEnd.coldConditions"
    ] == "tier-count:1"
    _validate_decision_references(_repository_contract())


def test_xmark02_row_cites_fr005_and_uses_saved_rule_values() -> None:
    """規定最終回のX行はFR-005を典拠にし、保存可能な規則だけを使う。"""
    contract = _repository_contract()
    register = _load_object(
        REPOSITORY_ROOT / "contracts/state-transition/clause_branch_register_v1.json"
    )
    row = next(item for item in contract["decisionRows"] if item["branchId"] == "XMARK-02")
    branch = next(item for item in register["branches"] if item["branchId"] == "XMARK-02")
    assert row["sourceClauseIds"] == branch["sourceClauseIds"] == [
        "req:FR-005", "req:FR-020",
    ]
    leaves = {leaf["axisId"]: leaf["value"] for leaf in _decision_leaves(row["precondition"])}
    assert leaves["gameEnd.coldConditions"] == "tier-count:0"
    assert leaves["gameEnd.extensionLimit"] == "finite:R"
    assert leaves["state.inning"] == "R"
    assert len([case for case in contract["cases"] if case["branchId"] == "XMARK-02"]) == 34
    _validate_decision_references(contract)


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
        leaf["value"] = "tier-count:3"
    with pytest.raises(AssertionError):
        _validate_decision_references(contract)


def test_walk_off_row_is_bound_to_fifth_role_and_fr005() -> None:
    """サヨナラの終了検知と表示種別を独立した台帳役割へ結ぶ。"""
    contract = _repository_contract()
    register = _load_object(
        REPOSITORY_ROOT / "contracts/state-transition/clause_branch_register_v1.json"
    )
    row = next(
        row for row in contract["decisionRows"]
        if row["branchId"] == "GAME-END-WALK-OFF"
    )
    assert register["gameEndOutcomeBranches"]["walkOff"] == row["branchId"]
    assert row["sourceClauseIds"] == ["req:FR-005", "req:FR-020", "req:F-1"]
    assert {leaf["axisId"]: leaf["value"] for leaf in _decision_leaves(row["precondition"])} == {
        "gameEnd.regulationInnings": 9,
        "gameEnd.coldConditions": "tier-count:0",
        "gameEnd.satisfiedColdTierCount": 0,
        "gameEnd.extensionLimit": "finite:R+1",
        "gameEnd.tiebreak": "none",
        "state.inning": "R",
        "state.half": "bottom",
        "state.score": "home-lead:M",
        "state.gameEnded": False,
        "event.operationKind": "per-pitch",
        "event.perPitch.kind": "batting-result",
        "event.perPitch.resultId": "本塁打",
        "state.outs": 0,
        "state.runners": "empty",
        "event.operationPayload": "not-applicable",
        "event.perPitch.pitchEventKind": "pitch-event",
        "event.perPitch.runnerEventPayload": "not-required",
        "event.perPitch.runnerAdvanceOverridesByRunner": "not-applied",
        "event.perPitch.thirdOutTimingByRunner": "not-required",
        "event.perPitch.interferenceRuling": "not-required",
        "event.perPitch.officialScoringPayload": "no-error",
        "event.perPitch.rbi.doublePlayRelayError": "not-required",
        "event.perPitch.rbi.runnerContinuityByRunner": "not-required",
        "event.perPitch.rbi.wouldScoreWithoutErrorByRunner": "not-required",
    }
    assert row["decision"] == {
        "outcome": "walk-off",
        "endConditionDetected": True,
        "lockFurtherPlayInput": True,
        "promptEndDeclaration": True,
        "automaticallyEndsGame": False,
        "xMark": "recorded-score",
    }
    assert "score" not in row["decision"]
    assert len([case for case in contract["cases"] if case["branchId"] == row["branchId"]]) == 10
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
        ("history.depth", 0),
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
    """終了規則と成立段数の5軸を境界注釈とともにexact-set射影する。"""
    schema = _schema()
    descriptor = _descriptor()
    projected = _projection_annotations(schema, "x-pitchlog-axis-id")
    expected = {axis["axisId"]: axis for axis in descriptor["gameEndAxes"]}

    assert set(projected) == set(expected)
    for axis_id, axis in expected.items():
        target = projected[axis_id]
        assert target["x-pitchlog-axis-classification"] == axis["classification"]
        assert target["x-pitchlog-coverage-bounds"] == axis["coverageBounds"]
        assert target["x-pitchlog-boundary-values"] == axis["boundaryValues"]
        if "invalidBoundaryValues" in axis:
            assert target["x-pitchlog-invalid-boundary-values"] == axis[
                "invalidBoundaryValues"
            ]
        else:
            assert "x-pitchlog-invalid-boundary-values" not in target


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


# --- 終了判定契約の由来記録(provenance)の検査器 ---------------------------------
# 置き場は本ファイル(両コア領域に登録済み)。T1の試験ファイルは変更しない。

PROVENANCE_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_provenance.py"
STATE_TRANSITION_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "contracts/state-transition/state_transition_contract_schema_v1.json"
)
STATE_TRANSITION_CONTRACT_PATH = (
    REPOSITORY_ROOT / "contracts/state-transition/state_transition_contract_v1.json"
)
GAME_END_SUBJECT_KIND = "normative-branch-or-state-effect"
REPOSITORY_ARTIFACT_AUTHOR = _load_object(
    REPOSITORY_ROOT / "docs/features/adr003-stage2-runtime/signatures/gate6-game-end.json"
)["artifactAuthorId"]
# 検査器が名前で import する依存を、未読み込みのときだけ同じ名前で読み込む。
for _dependency_name, _dependency_path in (
    ("check_input_axes_descriptor", DESCRIPTOR_CHECKER_PATH),
    (
        "check_vocabulary_manifest",
        REPOSITORY_ROOT / "scripts/check_vocabulary_manifest.py",
    ),
):
    if _dependency_name not in sys.modules:
        _load_module(_dependency_name, _dependency_path)
provenance_checker = _load_module(
    "game_end_provenance_checker", PROVENANCE_CHECKER_PATH
)


DEFINITION_REFERENCE = re.compile(r"^#/\$defs/(?P<name>[^/]+)$")


def _schema_references(value: object) -> list[str]:
    """schemaの値に現れる ``$ref`` の値を、入れ子を再帰でたどって返す。"""
    if isinstance(value, dict):
        found = [value["$ref"]] if isinstance(value.get("$ref"), str) else []
        for item in value.values():
            found.extend(_schema_references(item))
        return found
    if isinstance(value, list):
        return [reference for item in value for reference in _schema_references(item)]
    return []


def _provenance_definition_closure(schema: Mapping[str, Any]) -> dict[str, Any]:
    """``$defs.provenance`` から ``$ref`` で到達する定義の閉包を返す。

    Raises:
        KeyError: 参照先の定義が無い場合。
        ValueError: ``#/$defs/<名前>`` 以外の形の参照がある場合(閉包の外を
            指しうるため照合できない)。
    """
    definitions = schema["$defs"]
    closure: dict[str, Any] = {}
    pending = ["provenance"]
    while pending:
        name = pending.pop()
        if name in closure:
            continue
        closure[name] = definitions[name]
        for reference in _schema_references(definitions[name]):
            match = DEFINITION_REFERENCE.fullmatch(reference)
            if match is None:
                raise ValueError(f"閉包の外を指しうる参照: {reference}")
            pending.append(match.group("name"))
    return closure


def _provenance_schema() -> dict[str, Any]:
    """由来記録の器を持つ終了判定契約schemaの写しを返す。"""
    return deepcopy(_schema())


def _provenance_container_drift(
    t1_schema: Mapping[str, Any], t2_schema: Mapping[str, Any]
) -> list[str]:
    """由来記録の器(閉包・policy・配置)のT1とのずれを列挙する。"""
    drift: list[str] = []
    t1_closure = _provenance_definition_closure(t1_schema)
    try:
        t2_closure = _provenance_definition_closure(t2_schema)
    except (KeyError, ValueError) as error:
        return [f"T2の閉包が解決できない: {error}"]
    if t1_closure != t2_closure:
        names = sorted(set(t1_closure) | set(t2_closure))
        drift.extend(
            f"$defs.{name}"
            for name in names
            if t1_closure.get(name) != t2_closure.get(name)
        )
    if t1_schema.get("x-pitchlog-provenance-policy") != t2_schema.get(
        "x-pitchlog-provenance-policy"
    ):
        drift.append("x-pitchlog-provenance-policy")
    if t2_schema.get("properties", {}).get("provenance") != {
        "$ref": "#/$defs/provenance"
    }:
        drift.append("properties.provenance")
    if "provenance" not in t2_schema.get("required", []):
        drift.append("required.provenance")
    return drift


def _verified_provenance() -> dict[str, Any]:
    """実施済みの主張として全項目を満たす合成の由来記録を返す。"""
    return {
        "subjectKind": GAME_END_SUBJECT_KIND,
        "sources": [{"sourceKind": "requirements", "sourceId": "req:FR-005"}],
        "authorId": "contract-author",
        "independentVerifierId": "independent-verifier",
        "independentReview": {
            "verifiedOn": "2026-10-17",
            "reviewerRole": "reviewer",
            "authorWorkExposure": "not-seen-before-source-review",
            "chronology": [
                {
                    "sequence": 1,
                    "actorId": "independent-verifier",
                    "activity": "典拠を確認した",
                }
            ],
            "findings": ["典拠が対象を支持する"],
        },
        "attestations": [
            {"attestationId": "direct-source-clause-review", "response": True},
            {
                "attestationId": "author-work-exposure",
                "response": "not-seen-before-source-review",
            },
            {"attestationId": "source-support-judgment", "response": True},
        ],
    }


def _not_performed_provenance() -> dict[str, Any]:
    """未実施の閉じた形の合成の由来記録を返す。"""
    provenance = _verified_provenance()
    del provenance["independentReview"]
    provenance["independentVerifierId"] = "not-performed"
    provenance["attestations"] = [
        {"attestationId": "source-support-judgment", "response": False},
        {"attestationId": "direct-source-clause-review", "response": False},
        {"attestationId": "author-work-exposure", "response": "not-performed"},
    ]
    return provenance


def _classify_game_end(provenance: Mapping[str, Any]) -> str:
    """合成schemaで終了判定契約の由来記録を分類する。"""
    return provenance_checker.classify_provenance(
        REPOSITORY_ROOT,
        provenance,
        schema_value=_provenance_schema(),
        contract_kind="game-end",
    )


def _attestation(provenance: dict[str, Any], attestation_id: str) -> dict[str, Any]:
    """宣誓項目を返す。"""
    return next(
        item
        for item in provenance["attestations"]
        if item["attestationId"] == attestation_id
    )


def test_game_end_verified_provenance_is_classified_verified() -> None:
    """全項目を満たす終了判定の由来記録を実施済みとして受理する(P4)。"""
    assert _classify_game_end(_verified_provenance()) == "verified"


def test_game_end_not_performed_closed_form_is_accepted() -> None:
    """未実施の閉じた形を宣誓の順序に依らず未実施として受理する。"""
    assert _classify_game_end(_not_performed_provenance()) == "not-performed"


def test_default_contract_kind_keeps_state_transition_schema() -> None:
    """種別を省略した検証は状況判定契約のschemaで行う(P2)。"""
    t1_record = deepcopy(_verified_provenance())
    t1_record["subjectKind"] = "normative-branch-or-state-effect"
    provenance_checker.validate_provenance(REPOSITORY_ROOT, t1_record)

    repository_record = _load_object(STATE_TRANSITION_CONTRACT_PATH)["provenance"]
    with pytest.raises(
        provenance_checker.ProvenanceCheckError,
        match="宣誓応答が充足値でない",
    ):
        provenance_checker.validate_provenance(REPOSITORY_ROOT, repository_record)
    assert (
        provenance_checker.classify_provenance(REPOSITORY_ROOT, repository_record)
        == "not-performed"
    )


def _same_author_and_verifier(provenance: dict[str, Any]) -> None:
    provenance["independentVerifierId"] = provenance["authorId"]
    provenance["independentReview"]["chronology"][0]["actorId"] = provenance[
        "authorId"
    ]


def _half_signed(provenance: dict[str, Any]) -> None:
    del provenance["independentReview"]
    provenance["attestations"] = _not_performed_provenance()["attestations"]


def _not_performed_with_review(provenance: dict[str, Any]) -> None:
    review = deepcopy(_verified_provenance()["independentReview"])
    provenance.update(_not_performed_provenance())
    provenance["independentReview"] = review


def _not_performed_with_satisfied_attestations(provenance: dict[str, Any]) -> None:
    attestations = deepcopy(_verified_provenance()["attestations"])
    provenance.update(_not_performed_provenance())
    provenance["attestations"] = attestations


def _conflicting_duplicate_attestation(provenance: dict[str, Any]) -> None:
    """矛盾する値の重複宣誓を足す(後の値が閉じた形に一致する並び)。"""
    provenance["attestations"] = [
        {"attestationId": "direct-source-clause-review", "response": False},
        {"attestationId": "author-work-exposure", "response": "not-performed"},
        {"attestationId": "source-support-judgment", "response": True},
        {"attestationId": "source-support-judgment", "response": False},
    ]


def _missing_attestation(provenance: dict[str, Any]) -> None:
    provenance["attestations"].pop()


def _duplicate_attestation(provenance: dict[str, Any]) -> None:
    provenance["attestations"].append(deepcopy(provenance["attestations"][0]))


def _unknown_attestation(provenance: dict[str, Any]) -> None:
    provenance["attestations"][0]["attestationId"] = "unknown-attestation"


def _review_missing(provenance: dict[str, Any]) -> None:
    del provenance["independentReview"]


def _chronology_not_contiguous(provenance: dict[str, Any]) -> None:
    provenance["independentReview"]["chronology"][0]["sequence"] = 2


def _verifier_not_in_chronology(provenance: dict[str, Any]) -> None:
    provenance["independentReview"]["chronology"][0]["actorId"] = "someone-else"


def _exposure_mismatch(provenance: dict[str, Any]) -> None:
    provenance["independentReview"]["authorWorkExposure"] = (
        "seen-before-source-review"
    )


def _unknown_source_kind(provenance: dict[str, Any]) -> None:
    provenance["sources"][0]["sourceKind"] = "unknown-source"


def _missing_requirement(provenance: dict[str, Any]) -> None:
    provenance["sources"][0]["sourceId"] = "req:NOT-EXISTS"


def _legacy_research_only(provenance: dict[str, Any]) -> None:
    provenance["sources"] = [
        {
            "sourceKind": "legacy-research",
            "sourceId": "docs/legacy/research/input-screen.md:70",
        }
    ]


def _unknown_subject_kind(provenance: dict[str, Any]) -> None:
    provenance["subjectKind"] = "unknown-subject"


def _reserved_value_spoof(provenance: dict[str, Any]) -> None:
    provenance["independentVerifierId"] = "not-performed"
    provenance["independentReview"]["chronology"][0]["actorId"] = "not-performed"


def _reserved_actor_only(provenance: dict[str, Any]) -> None:
    provenance["independentReview"]["chronology"].append(
        {"sequence": 2, "actorId": "not-performed", "activity": "記録した"}
    )


def _reserved_response_only(provenance: dict[str, Any]) -> None:
    _attestation(provenance, "author-work-exposure")["response"] = "not-performed"


def _reserved_author(provenance: dict[str, Any]) -> None:
    provenance["authorId"] = "not-performed"


VERIFIED_RECORD_NEGATIVES = {
    "S1-same-author-verifier": (_same_author_and_verifier, "作成者と独立確認者"),
    "S2-half-signed": (
        _half_signed,
        "予約値not-performedを含むが未実施の閉じた形と一致しない: independentVerifierId",
    ),
    "S4-missing-attestation": (_missing_attestation, "宣誓項目がexact-set不一致"),
    "S4-duplicate-attestation": (_duplicate_attestation, "宣誓項目が重複"),
    "S4-unknown-attestation": (_unknown_attestation, "宣誓項目がexact-set不一致"),
    "S5-review-missing": (
        _review_missing,
        "provenance.independentReviewがobjectでない",
    ),
    "S6-chronology-order": (_chronology_not_contiguous, "連続順序でない"),
    "S6-verifier-not-actor": (_verifier_not_in_chronology, "actorIdに現れない"),
    "S7-exposure-mismatch": (
        _exposure_mismatch,
        "作業結果の閲覧順序とauthor-work-exposure宣誓が一致しない",
    ),
    "S8-unknown-source-kind": (_unknown_source_kind, "未知の典拠種別"),
    "S8-missing-requirement": (_missing_requirement, "典拠IDが実在しない"),
    "S8-legacy-research-only": (_legacy_research_only, "優先典拠が無い"),
    "S9-unknown-subject-kind": (_unknown_subject_kind, "未知の対象種別"),
    "S11-reserved-spoof": (_reserved_value_spoof, "未実施の閉じた形と一致しない"),
    "S11a-reserved-actor-only": (_reserved_actor_only, "未実施の閉じた形と一致しない"),
    "S11b-reserved-response-only": (
        _reserved_response_only,
        "未実施の閉じた形と一致しない",
    ),
    "S11c-reserved-author": (_reserved_author, "作成者IDに予約値"),
}


@pytest.mark.parametrize("case_id", sorted(VERIFIED_RECORD_NEGATIVES))
def test_game_end_invalid_signature_is_red(case_id: str) -> None:
    """終了判定の不正署名・偽の典拠・予約値の偽装を拒否する(S1〜S11c)。"""
    change, message = VERIFIED_RECORD_NEGATIVES[case_id]
    provenance = _verified_provenance()
    change(provenance)

    with pytest.raises(provenance_checker.ProvenanceCheckError, match=message):
        _classify_game_end(provenance)


NOT_PERFORMED_RECORD_NEGATIVES = {
    "S3-not-performed-with-review": (
        _not_performed_with_review,
        "予約値not-performedを含むが未実施の閉じた形と一致しない: independentReviewがある",
    ),
    "S4p-conflicting-duplicate-attestation": (
        _conflicting_duplicate_attestation,
        "宣誓項目が重複している: 'source-support-judgment'",
    ),
    "S3b-not-performed-with-satisfied-attestations": (
        _not_performed_with_satisfied_attestations,
        "未実施の閉じた形と一致しない: attestations",
    ),
    "S8p-unknown-source-kind": (_unknown_source_kind, "未知の典拠種別"),
    "S8p-missing-requirement": (_missing_requirement, "典拠IDが実在しない"),
    "S10p-legacy-research-only": (_legacy_research_only, "優先典拠が無い"),
    "S9p-unknown-subject-kind": (_unknown_subject_kind, "未知の対象種別"),
    "S11c-reserved-author": (_reserved_author, "作成者IDに予約値"),
}


@pytest.mark.parametrize("case_id", sorted(NOT_PERFORMED_RECORD_NEGATIVES))
def test_game_end_not_performed_record_still_checks_sources(case_id: str) -> None:
    """未実施の記録でも典拠・対象種別・閉じた形を検証する(S3・S8'〜S10')。"""
    change, message = NOT_PERFORMED_RECORD_NEGATIVES[case_id]
    provenance = _not_performed_provenance()
    change(provenance)

    with pytest.raises(provenance_checker.ProvenanceCheckError, match=message):
        _classify_game_end(provenance)


def test_game_end_provenance_schema_rejects_unknown_key() -> None:
    """合成schemaで由来記録の未知キーを拒否する(器の閉じ方)。"""
    provenance = _verified_provenance()
    provenance["unexpected"] = True

    with pytest.raises(
        provenance_checker.ProvenanceCheckError, match="未知キー: .*unexpected"
    ):
        _classify_game_end(provenance)


def test_not_performed_form_requires_declared_attestation_items() -> None:
    """宣誓項目の宣言が閉じた形とずれたら未実施の記録も拒否する。"""
    schema = _provenance_schema()
    items = schema["x-pitchlog-provenance-policy"]["attestationItems"]
    items["extra-attestation"] = {
        "acceptedResponses": [True],
        "humanMeaning": "追加の宣誓",
    }

    with pytest.raises(
        provenance_checker.ProvenanceCheckError,
        match="未実施の閉じた形が宣誓項目の宣言とexact-set不一致",
    ):
        provenance_checker.classify_provenance(
            REPOSITORY_ROOT,
            _not_performed_provenance(),
            schema_value=schema,
            contract_kind="game-end",
        )


def test_unregistered_contract_kind_is_red() -> None:
    """登録表に無い契約種別を拒否する。"""
    with pytest.raises(
        provenance_checker.ProvenanceCheckError, match="登録表に無い契約種別"
    ):
        provenance_checker.classify_provenance(
            REPOSITORY_ROOT, _verified_provenance(), contract_kind="unknown"
        )


def test_game_end_provenance_container_matches_state_transition() -> None:
    """T2の由来記録の器(閉包・policy・配置)がT1と完全一致する(D1〜D3)。"""
    t1_schema = _load_object(STATE_TRANSITION_SCHEMA_PATH)
    assert set(_provenance_definition_closure(t1_schema)) == {
        "provenance",
        "provenanceIndependentReview",
        "provenanceReviewEvent",
        "provenanceSource",
        "provenanceAttestation",
    }
    assert _provenance_container_drift(t1_schema, _schema()) == []


def _drift_definition(schema: dict[str, Any]) -> None:
    schema["$defs"]["provenanceReviewEvent"]["required"].append("extra")


def _drop_definition(schema: dict[str, Any]) -> None:
    del schema["$defs"]["provenanceReviewEvent"]


def _drift_policy(schema: dict[str, Any]) -> None:
    schema["x-pitchlog-provenance-policy"]["subjectKinds"]["extra-kind"] = {
        "sufficientSourceKinds": ["requirements"]
    }


def _non_definition_reference(schema: dict[str, Any]) -> None:
    review = schema["$defs"]["provenanceIndependentReview"]
    review["properties"]["chronology"]["items"] = {"$ref": "#/x-shared/event"}


def _drop_required(schema: dict[str, Any]) -> None:
    schema["required"].remove("provenance")


def _drop_property(schema: dict[str, Any]) -> None:
    del schema["properties"]["provenance"]


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (_drift_definition, ["$defs.provenanceReviewEvent"]),
        (_drop_definition, ["T2の閉包が解決できない: 'provenanceReviewEvent'"]),
        (_drift_policy, ["x-pitchlog-provenance-policy"]),
        (
            _non_definition_reference,
            ["T2の閉包が解決できない: 閉包の外を指しうる参照: #/x-shared/event"],
        ),
        (_drop_required, ["required.provenance"]),
        (_drop_property, ["properties.provenance"]),
    ],
    ids=[
        "D1-drift",
        "D1-drop",
        "D2-policy",
        "D1-non-definition-reference",
        "D3-required",
        "D3-property",
    ],
)
def test_game_end_provenance_container_drift_is_detected(
    change: Any, expected: list[str]
) -> None:
    """器の閉包・policy・配置のずれを照合で検出する(D1〜D3)。"""
    schema = deepcopy(_schema())
    change(schema)

    assert (
        _provenance_container_drift(_load_object(STATE_TRANSITION_SCHEMA_PATH), schema)
        == expected
    )


@pytest.mark.parametrize("change", ["drop-policy", "drop-required"])
def test_checker_rejects_schema_without_provenance_declaration(change: str) -> None:
    """policyや必須宣言を外したschemaでは検査器が検証を拒否する(D3)。"""
    schema = _provenance_schema()
    if change == "drop-policy":
        del schema["x-pitchlog-provenance-policy"]
    else:
        schema["required"].remove("provenance")

    with pytest.raises(provenance_checker.ProvenanceCheckError):
        provenance_checker.classify_provenance(
            REPOSITORY_ROOT,
            _not_performed_provenance(),
            schema_value=schema,
            contract_kind="game-end",
        )


# 由来記録に出さない構造化引用(policyに受ける典拠種別が無い — research.md 6節の6)
UNRECORDED_CITATIONS = {"adr:D-11"}
SOURCE_KIND_BY_PREFIX = {
    "req": "requirements",
    "obr": "official-baseball-rules",
}


def _structured_clause_citations(value: object) -> set[str]:
    """契約に現れる ``sourceClauseIds`` の値を、接頭辞を問わずすべて集める。"""
    if isinstance(value, dict):
        found: set[str] = set()
        for key, item in value.items():
            if key == "sourceClauseIds":
                assert isinstance(item, list)
                found.update(item)
            else:
                found |= _structured_clause_citations(item)
        return found
    if isinstance(value, list):
        return {
            citation for item in value for citation in _structured_clause_citations(item)
        }
    return set()


def test_structured_citation_population_catches_unrecorded_prefixes() -> None:
    """構造化引用の母集団は、req:以外の典拠が増えれば記録漏れとして現れる。"""
    body = {
        key: value
        for key, value in deepcopy(_repository_contract()).items()
        if key != "provenance"
    }
    body["validationErrors"][0]["sourceClauseIds"].append("obr:7.01(a)")
    body["validationErrors"][1]["sourceClauseIds"].append("adr:D-12")
    recorded = {
        source["sourceId"] for source in _repository_contract()["provenance"]["sources"]
    }

    assert _structured_clause_citations(body) - recorded == {
        "adr:D-11",
        "adr:D-12",
        "obr:7.01(a)",
    }


def test_repository_game_end_provenance_is_not_performed() -> None:
    """実資産の終了判定契約は未実施の閉じた形と、契約が引く要件書の典拠を記録する。"""
    contract = _repository_contract()
    provenance = contract["provenance"]

    assert provenance["subjectKind"] == "normative-branch-or-state-effect"
    assert provenance["authorId"] == REPOSITORY_ARTIFACT_AUTHOR
    assert "independentReview" not in provenance
    assert (
        provenance_checker.classify_provenance(
            REPOSITORY_ROOT, provenance, contract_kind="game-end"
        )
        == "not-performed"
    )
    body = {key: value for key, value in contract.items() if key != "provenance"}
    cited = _structured_clause_citations(body)
    recorded = {source["sourceId"] for source in provenance["sources"]}
    # 母集団は接頭辞を問わない構造化引用(sourceClauseIds)のすべて。記録しない典拠は
    # 閉じた除外集合だけ(research.md 6節の6)。地の文(remarks)の言及は母集団に含めない
    assert cited - recorded == UNRECORDED_CITATIONS
    assert recorded <= cited
    assert len(recorded) == len(provenance["sources"]) == 21
    for source in provenance["sources"]:
        prefix = source["sourceId"].split(":", 1)[0]
        assert SOURCE_KIND_BY_PREFIX[prefix] == source["sourceKind"]


def test_contract_without_provenance_violates_schema() -> None:
    """由来記録の無い終了判定契約をschemaで拒否する(N1)。"""
    contract = _minimal_contract()
    del contract["provenance"]

    with pytest.raises(
        schema_checker.DescriptorCheckError, match="必須キー不足: .*provenance"
    ):
        _validate_contract(contract)


@pytest.mark.parametrize("value", [None, [], {}], ids=["null", "array", "empty-object"])
def test_contract_with_malformed_provenance_violates_schema(value: Any) -> None:
    """由来記録がobjectでない、または空のときschemaで拒否する(N2)。"""
    contract = _minimal_contract()
    contract["provenance"] = value

    with pytest.raises(schema_checker.DescriptorCheckError):
        _validate_contract(contract)


@pytest.mark.parametrize(
    "field",
    ["subjectKind", "sources", "authorId", "independentVerifierId", "attestations"],
)
def test_provenance_missing_required_field_violates_schema(field: str) -> None:
    """由来記録の必須5キーのいずれかを欠くとschemaで拒否する(N3)。"""
    contract = _minimal_contract()
    del contract["provenance"][field]

    with pytest.raises(
        schema_checker.DescriptorCheckError, match=rf"必須キー不足: .*{field}"
    ):
        _validate_contract(contract)


def test_provenance_unknown_field_violates_schema() -> None:
    """由来記録の未知キーをschemaで拒否する(N4)。"""
    contract = _minimal_contract()
    contract["provenance"]["unexpected"] = True

    with pytest.raises(
        schema_checker.DescriptorCheckError, match="未知キー: .*unexpected"
    ):
        _validate_contract(contract)


def test_registry_matches_declared_contract_list() -> None:
    """登録表の契約集合が契約一覧の宣言と一致する(閉包)。"""
    provenance_checker.check_registry_closure(REPOSITORY_ROOT)


@pytest.mark.parametrize("change", ["drop-game-end", "extra-contract"])
def test_registry_closure_drift_is_red(change: str) -> None:
    """登録表から契約が欠けても、余分な契約があっても拒否する。"""
    registry = dict(provenance_checker.CONTRACTS)
    if change == "drop-game-end":
        del registry["game-end"]
    else:
        registry["extra"] = (
            PurePosixPath("contracts/state-transition/extra_contract_v1.json"),
            PurePosixPath("contracts/state-transition/extra_schema_v1.json"),
            "追加契約",
        )

    with pytest.raises(
        provenance_checker.ProvenanceCheckError, match="exact-set不一致"
    ):
        provenance_checker.check_registry_closure(REPOSITORY_ROOT, registry)


def test_repository_check_rejects_registry_closure_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--repositoryの経路でも登録表と契約一覧のずれを拒否する。"""
    registry = dict(provenance_checker.CONTRACTS)
    del registry["game-end"]
    monkeypatch.setattr(provenance_checker, "CONTRACTS", registry)

    with pytest.raises(
        provenance_checker.ProvenanceCheckError, match="exact-set不一致"
    ):
        provenance_checker.check_repository(REPOSITORY_ROOT)


def test_main_passes_contract_kind_to_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLIは登録表で決めた契約種別で検証する(種別の取り違えを防ぐ)。"""
    calls: list[str] = []

    def spy(root: Path, provenance: Mapping[str, Any], **kwargs: Any) -> None:
        calls.append(kwargs["contract_kind"])

    monkeypatch.setattr(provenance_checker, "validate_provenance", spy)
    contract = _repository_contract()
    contract["provenance"] = _verified_provenance()
    monkeypatch.setattr(
        provenance_checker.descriptor_checker,
        "load_json",
        lambda path, label: deepcopy(contract),
    )

    assert provenance_checker.main([str(CONTRACT_PATH)]) == 0
    assert calls == ["game-end"]


@pytest.mark.parametrize(
    "argv", [[], [str(CONTRACT_PATH), "--repository"]], ids=["none", "both"]
)
def test_main_requires_exactly_one_target(argv: list[str]) -> None:
    """CLIは契約JSONと--repositoryのどちらか一方だけを受け付ける。"""
    with pytest.raises(SystemExit) as raised:
        provenance_checker.main(argv)
    assert raised.value.code == 2


def test_repository_check_lists_both_contracts_as_not_performed() -> None:
    """--repositoryの経路で両契約を未実施として列挙する(P3)。"""
    assert provenance_checker.check_repository(REPOSITORY_ROOT) == {
        "state-transition": "not-performed",
        "game-end": "not-performed",
    }
    assert provenance_checker.main(["--repository"]) == 0


def test_repository_check_reports_missing_game_end_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """終了判定契約から由来記録が消えたら--repositoryの経路で赤にする(未記載)。"""
    original = provenance_checker.descriptor_checker.load_json

    def load_without_provenance(path: Path, label: str) -> object:
        value = original(path, label)
        if Path(path).resolve() == CONTRACT_PATH.resolve():
            assert isinstance(value, dict)
            value = {key: item for key, item in value.items() if key != "provenance"}
        return value

    monkeypatch.setattr(
        provenance_checker.descriptor_checker, "load_json", load_without_provenance
    )

    with pytest.raises(
        provenance_checker.ProvenanceCheckError,
        match="終了判定契約にprovenanceが無い",
    ):
        provenance_checker.check_repository(REPOSITORY_ROOT)


def test_contract_kind_for_path_rejects_unregistered_path(tmp_path: Path) -> None:
    """登録表に無いパスの契約を種別判定で拒否する(N6)。"""
    assert (
        provenance_checker.contract_kind_for_path(REPOSITORY_ROOT, CONTRACT_PATH)
        == "game-end"
    )
    unregistered = tmp_path / "game_end_contract_v1.json"
    unregistered.write_text(CONTRACT_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(
        provenance_checker.ProvenanceCheckError, match="登録表に無い契約"
    ):
        provenance_checker.contract_kind_for_path(REPOSITORY_ROOT, unregistered)
    assert provenance_checker.main([str(unregistered)]) == 1


@pytest.mark.parametrize("contract_kind", ["state-transition", "game-end"])
@pytest.mark.parametrize("entry_point", ["validator", "single-cli", "repository"])
@pytest.mark.parametrize("reserved_location", ["author", "verifier", "extra-actor"])
def test_reserved_identity_is_rejected_at_every_entry_point(
    monkeypatch: pytest.MonkeyPatch,
    contract_kind: str,
    entry_point: str,
    reserved_location: str,
) -> None:
    """実施済み主張の予約ID偽装を両契約の全検査入口で拒否する。"""
    provenance = _verified_provenance()
    if reserved_location == "author":
        provenance["authorId"] = "not-performed"
    elif reserved_location == "verifier":
        provenance["independentVerifierId"] = "not-performed"
        provenance["independentReview"]["chronology"][0]["actorId"] = "not-performed"
    else:
        provenance["independentReview"]["chronology"].append(
            {"sequence": 2, "actorId": "not-performed", "activity": "追加記録"}
        )
    contract_path = REPOSITORY_ROOT / provenance_checker.CONTRACTS[contract_kind][0]
    original_load = provenance_checker.descriptor_checker.load_json

    def load_with_forged_record(path: Path, label: str) -> Any:
        value = original_load(path, label)
        if Path(path) == contract_path:
            value = deepcopy(value)
            value["provenance"] = deepcopy(provenance)
        return value

    monkeypatch.setattr(
        provenance_checker.descriptor_checker, "load_json", load_with_forged_record
    )
    if entry_point == "single-cli":
        assert provenance_checker.main([str(contract_path)]) == 1
        return
    with pytest.raises(provenance_checker.ProvenanceCheckError, match="予約値not-performed"):
        if entry_point == "validator":
            provenance_checker.validate_provenance(
                REPOSITORY_ROOT, provenance, contract_kind=contract_kind
            )
        else:
            provenance_checker.check_repository(REPOSITORY_ROOT)
