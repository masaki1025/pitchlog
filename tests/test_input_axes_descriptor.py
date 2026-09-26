"""入力軸descriptorの構造とdigest規則を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_input_axes_descriptor.py"
FREEZE_SCRIPT = REPOSITORY_ROOT / "scripts" / "state_transition_freeze.py"


def _load_module(name: str, path: Path) -> Any:
    """テスト対象をsys.path変更なしでモジュールとして読む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_module("state_transition_freeze", FREEZE_SCRIPT)
checker = _load_module("check_input_axes_descriptor_under_test", SCRIPT)
DESCRIPTOR_PATH = REPOSITORY_ROOT / checker.DESCRIPTOR_PATH
SCHEMA_PATH = REPOSITORY_ROOT / checker.SCHEMA_PATH
SOURCE_CLAUSE_IDS = checker.load_source_clause_ids(REPOSITORY_ROOT)
LEGACY_DATA_LAYER_PATH = REPOSITORY_ROOT / "docs/legacy/research/data-layer.md"


def _load_object(path: Path) -> dict[str, Any]:
    """JSON objectを読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _descriptor() -> dict[str, Any]:
    """リポジトリのdescriptorを読む。"""
    return _load_object(DESCRIPTOR_PATH)


def _schema() -> dict[str, Any]:
    """リポジトリのdescriptor schemaを読む。"""
    return _load_object(SCHEMA_PATH)


def _criteria() -> Any:
    """資産側宣言からdescriptor検査基準を読む。"""
    return checker.load_descriptor_criteria(_descriptor())


def _with_digest(descriptor: dict[str, Any]) -> dict[str, Any]:
    """descriptorへ現在内容のdigestを設定して返す。"""
    descriptor["digest"] = checker.compute_descriptor_digest(descriptor)
    return descriptor


def _validate(descriptor: dict[str, Any]) -> None:
    """リポジトリのschemaと実在条文IDを用いてdescriptorを検証する。"""
    checker.validate_descriptor_document(descriptor, _schema(), SOURCE_CLAUSE_IDS)


def test_repository_descriptor_passes_schema_and_digest_validation() -> None:
    """リポジトリ実物が閉じたschemaとdigest検査を通る。"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(REPOSITORY_ROOT)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "input-axes-descriptor: OK\n"
    assert result.stderr == ""


def test_schema_defines_the_complete_top_level_and_closed_axis_enum() -> None:
    """schemaが全トップレベル列と3分類の閉じた集合を定める。"""
    schema = _schema()
    descriptor = _descriptor()

    assert schema["version"] == checker.SCHEMA_PATH.stem
    assert descriptor["version"] == checker.DESCRIPTOR_PATH.stem
    assert set(schema["required"]) == _criteria().top_level_fields
    assert set(schema["properties"]) == _criteria().top_level_fields
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["axisClassification"]["enum"] == [
        "finite-enumerable",
        "boundary-partition",
        "non-finite",
    ]


def test_digest_is_reproducible_and_independent_of_object_key_order() -> None:
    """同じJSON値はobjectの記述順に依存せず同じdigestになる。"""
    descriptor = _descriptor()
    reordered = dict(reversed(tuple(descriptor.items())))

    first = checker.compute_descriptor_digest(descriptor)
    second = checker.compute_descriptor_digest(descriptor)
    reordered_digest = checker.compute_descriptor_digest(reordered)

    assert first == descriptor["digest"]
    assert second == first
    assert reordered_digest == first


@pytest.mark.parametrize(
    ("axis", "classification"),
    [
        (
            {
                "axisId": "schema.finiteProbe",
                "sourceClauseId": "adr:D-11",
                "classification": "finite-enumerable",
                "values": [False, True],
            },
            "finite-enumerable",
        ),
        (
            {
                "axisId": "schema.boundaryProbe",
                "sourceClauseId": "adr:D-11",
                "classification": "boundary-partition",
                "boundaryValues": [0, 1, "D"],
            },
            "boundary-partition",
        ),
        (
            {
                "axisId": "schema.nonFiniteProbe",
                "sourceClauseId": "req:FR-006",
                "classification": "non-finite",
                "nonFiniteReason": "実行時の履歴深さに上限を置かないため",
            },
            "non-finite",
        ),
    ],
)
def test_each_closed_axis_shape_is_accepted(
    axis: dict[str, Any], classification: str
) -> None:
    """schema上の3分類がそれぞれ対応する値域表現だけを持てる。"""
    schema = _schema()

    checker._validate_instance(axis, schema["$defs"]["axis"], schema, "$.axis")

    assert axis["classification"] == classification


def test_changing_only_source_clause_id_changes_digest_and_is_red() -> None:
    """由来条文IDだけの差し替えを保存済みdigestとの不一致で拒否する。"""
    descriptor = _descriptor()
    _with_digest(descriptor)
    baseline_digest = descriptor["digest"]
    _validate(descriptor)

    changed = copy.deepcopy(descriptor)
    axis = next(
        axis
        for axis in changed["stateTransitionAxes"]
        if axis["axisId"] == "state.tiebreakActive"
    )
    axis["sourceClauseId"] = "req:FR-010"
    changed_digest = checker.compute_descriptor_digest(changed)

    assert changed_digest != baseline_digest
    with pytest.raises(checker.DescriptorCheckError, match="digest不一致"):
        _validate(changed)


def test_requirement_clause_cannot_be_rebound_to_same_named_adr_clause() -> None:
    """同名D-4を誤った正本名前空間へ差し替えても実在だけでは通さない。"""
    descriptor = _descriptor()
    axis = next(
        item
        for item in descriptor["stateTransitionAxes"]
        if item["axisId"] == "event.perPitch.resultId"
    )
    axis["sourceClauseId"] = "adr:D-4"
    _with_digest(descriptor)

    with pytest.raises(
        checker.DescriptorCheckError,
        match="同名条文IDの名前空間が誤っている",
    ):
        _validate(descriptor)


def test_state_transition_axes_match_d11_inventory_and_sources() -> None:
    """D-11の状態・イベント・履歴文脈軸を逐条対応で全て収容する。"""
    descriptor = _descriptor()
    axes = {axis["axisId"]: axis for axis in descriptor["stateTransitionAxes"]}
    expected = {
        "state.half": ("req:FR-005", "finite-enumerable"),
        "state.count.strikes": ("req:E-1", "finite-enumerable"),
        "state.count.balls": ("req:E-1", "finite-enumerable"),
        "state.outs": ("req:FR-005", "finite-enumerable"),
        "state.runners": ("req:E-1", "finite-enumerable"),
        "state.battingOrder": ("req:FR-005", "finite-enumerable"),
        "state.tiebreakActive": ("req:FR-009", "finite-enumerable"),
        "state.gameEnded": ("req:FR-010", "finite-enumerable"),
        "state.inning": ("req:F-1", "boundary-partition"),
        "state.score": ("req:F-1", "boundary-partition"),
        "event.operationKind": ("req:4.0-4", "finite-enumerable"),
        "event.operationPayload": ("adr:D-8", "boundary-partition"),
        "event.perPitch.kind": ("req:E-1", "finite-enumerable"),
        "event.perPitch.pitchEventKind": (
            "req:4.0-2",
            "finite-enumerable",
        ),
        "event.perPitch.resultId": ("req:D-4", "finite-enumerable"),
        "event.perPitch.runnerEventPayload": (
            "req:FR-004",
            "boundary-partition",
        ),
        "event.perPitch.runnerAdvanceOverridesByRunner": (
            "req:FR-003",
            "boundary-partition",
        ),
        "event.perPitch.thirdOutTimingByRunner": (
            "req:FR-003",
            "boundary-partition",
        ),
        "event.perPitch.interferenceRuling": (
            "req:FR-004",
            "boundary-partition",
        ),
        "event.perPitch.officialScoringPayload": (
            "req:FR-004",
            "boundary-partition",
        ),
        "event.perPitch.rbi.doublePlayRelayError": (
            "req:FR-003",
            "finite-enumerable",
        ),
        "event.perPitch.rbi.runnerContinuityByRunner": (
            "req:FR-003",
            "boundary-partition",
        ),
        "event.perPitch.rbi.wouldScoreWithoutErrorByRunner": (
            "req:FR-003",
            "boundary-partition",
        ),
        "history.depth": ("adr:D-11", "boundary-partition"),
        "history.composition": ("adr:D-11", "boundary-partition"),
        "history.scenarioLength": ("adr:D-11", "boundary-partition"),
    }

    assert {
        axis_id: (axis["sourceClauseId"], axis["classification"])
        for axis_id, axis in axes.items()
    } == expected
    assert all(source_id in SOURCE_CLAUSE_IDS for source_id, _ in expected.values())
    assert all(
        source_id in SOURCE_CLAUSE_IDS
        for axis in axes.values()
        for source_id in axis.get("supportingClauseIds", [])
    )
    assert axes["event.perPitch.resultId"]["supportingClauseIds"] == ["req:4.0-3"]
    assert axes["event.perPitch.pitchEventKind"]["values"] == [
        "pitch-event",
        "non-pitch-event",
    ]
    assert "supportingClauseIds" not in axes["event.perPitch.pitchEventKind"]
    assert (
        "supportingClauseIds"
        not in axes["event.perPitch.runnerAdvanceOverridesByRunner"]
    )
    assert "supportingClauseIds" not in axes[
        "event.perPitch.officialScoringPayload"
    ]
    assert axes["event.perPitch.thirdOutTimingByRunner"]["supportingClauseIds"] == [
        "req:OUT3-01",
        "req:OUT3-02",
        "req:OUT3-03",
        "req:OUT3-04",
        "req:OUT3-05",
    ]
    assert axes["event.perPitch.thirdOutTimingByRunner"]["boundaryValues"] == [
        "not-required",
        "single-runner-home-before-third-out",
        "single-runner-not-before-third-out",
        "multiple-runners-mixed-timing",
    ]
    assert axes["event.perPitch.interferenceRuling"]["supportingClauseIds"] == [
        "req:INT-01",
        "req:INT-02",
        "req:INT-03",
        "req:INT-04",
        "req:INT-05",
        "req:INT-06",
        "req:INT-07",
    ]
    assert axes["event.perPitch.interferenceRuling"]["boundaryValues"] == [
        "not-required",
        "batting:penalty-award",
        "batting:play-result-with-resultId",
        "obstruction:play-on-obstructed-runner-with-awarded-destinations",
        "obstruction:no-play-on-obstructed-runner-with-awarded-destinations-and-out-targets",
        "offensive-interference:batter-included-with-out-targets-and-return-bases",
        "offensive-interference:runner-only-with-out-targets-and-return-bases",
    ]
    assert axes["state.inning"]["boundaryValues"] == [
        1,
        "N-1",
        "N",
        "N+1",
        "R-1",
        "R",
        "R+1",
        "L-1",
        "L",
        "L+1",
    ]
    assert axes["state.score"]["boundaryValues"] == [
        "away-lead:M+1",
        "away-lead:M",
        "away-lead:M-1",
        "tie",
        "home-lead:M-1",
        "home-lead:M",
        "home-lead:M+1",
    ]
    assert axes["history.depth"]["boundaryValues"] == [0, 1, 2, "D"]
    assert axes["history.scenarioLength"]["boundaryValues"] == [
        1,
        2,
        "D",
        "D+1",
    ]
    assert all(
        axis["classification"] == "finite-enumerable"
        for axis_id, axis in axes.items()
        if axis_id.startswith("event.")
        and axis_id
        not in {
            "event.operationPayload",
            "event.perPitch.runnerEventPayload",
            "event.perPitch.runnerAdvanceOverridesByRunner",
            "event.perPitch.thirdOutTimingByRunner",
            "event.perPitch.interferenceRuling",
            "event.perPitch.officialScoringPayload",
            "event.perPitch.rbi.runnerContinuityByRunner",
            "event.perPitch.rbi.wouldScoreWithoutErrorByRunner",
        }
    )


def test_observation_input_axes_generate_nonzero_coverage_obligations() -> None:
    """条件付き観測入力も不在分岐を含めてcoverage座標を生成する。"""
    axes = {
        axis["axisId"]: axis for axis in _descriptor()["stateTransitionAxes"]
    }

    assert (
        checker.coverage_obligation_count(
            axes["event.perPitch.thirdOutTimingByRunner"]
        )
        == 4
    )
    assert (
        checker.coverage_obligation_count(
            axes["event.perPitch.interferenceRuling"]
        )
        == 7
    )
    assert checker.coverage_obligation_count(
        axes["event.perPitch.rbi.doublePlayRelayError"]
    ) == 3
    assert checker.coverage_obligation_count(
        axes["event.perPitch.rbi.runnerContinuityByRunner"]
    ) == 4
    assert checker.coverage_obligation_count(
        axes["event.perPitch.rbi.wouldScoreWithoutErrorByRunner"]
    ) == 4
    assert checker.coverage_obligation_count(
        axes["event.perPitch.runnerAdvanceOverridesByRunner"]
    ) == 6
    assert checker.coverage_obligation_count(
        axes["event.perPitch.officialScoringPayload"]
    ) == 3


def test_structured_inputs_separate_stage1_schema_from_stage2_capability() -> None:
    """段階1で閉じる写像と段階2へ送る表現能力を混同しない。"""
    axes = {
        axis["axisId"]: axis for axis in _descriptor()["stateTransitionAxes"]
    }

    structured_axes = {
        axis_id for axis_id, axis in axes.items() if "valueSchema" in axis
    }
    assert structured_axes == _criteria().exact_structured_axis_ids
    assert (
        axes["event.perPitch.thirdOutTimingByRunner"]["valueSchema"][
            "additionalProperties"
        ]
        is False
    )
    assert set(
        axes["event.perPitch.thirdOutTimingByRunner"]["valueSchema"]["properties"]
    ) == {"batter", "first", "second", "third"}
    deferred_axes = {
        axis_id
        for axis_id, axis in axes.items()
        if "representationCapability" in axis
    }
    assert deferred_axes == frozenset(_criteria().deferred_structured_axis_kinds)
    assert all("valueSchema" not in axes[axis_id] for axis_id in deferred_axes)
    assert axes["event.perPitch.runnerEventPayload"]["representationCapability"][
        "dimensions"
    ] == ["event-kind", "runner-identity", "outcome", "destination", "out-kind"]
    assert "target-identity" in axes["event.perPitch.interferenceRuling"][
        "representationCapability"
    ]["dimensions"]
    assert axes["event.perPitch.runnerAdvanceOverridesByRunner"][
        "representationCapability"
    ]["dimensions"] == ["runner-identity", "outcome", "destination"]
    assert axes["event.perPitch.officialScoringPayload"][
        "representationCapability"
    ]["dimensions"] == ["error-count", "fielder-reference"]


def test_payload_internal_constraints_are_explicitly_deferred_to_stage2() -> None:
    """保証しない内部制約を宣言し、段階2の必須成果物まで閉じる。"""
    declaration = _descriptor()["stage2ExternalConstraints"]

    assert (
        set(declaration["payloadAxisIds"])
        == frozenset(_criteria().deferred_structured_axis_kinds)
    )
    assert (
        set(declaration["constraintClasses"])
        == _criteria().stage2_constraint_classes
    )
    assert (
        set(declaration["requiredArtifacts"])
        == _criteria().stage2_required_artifacts
    )
    assert declaration["sourceClauseId"] == "adr:D-11"
    assert declaration["axisCombinationScope"] == "all-state-transition-axes"


@pytest.mark.parametrize(
    "constraint_class",
    [
        "payload-string-policy-reconciliation",
        "stat-flag-derivation-rules",
        "third-out-type-observation-input",
        "official-scorer-judgment-inputs",
    ],
)
def test_stage2_constraint_class_cannot_be_omitted(
    constraint_class: str,
) -> None:
    """段階2へ送った制約クラスを1件でも落とすとfailする。"""
    descriptor = _descriptor()
    descriptor["stage2ExternalConstraints"]["constraintClasses"].remove(
        constraint_class
    )
    _with_digest(descriptor)

    with pytest.raises(
        checker.DescriptorCheckError,
        match="段階2へ委任した制約種別がexact-set不一致",
    ):
        _validate(descriptor)


def test_fr040_conditional_members_cannot_drift_independently() -> None:
    """状態補正の操作種別・payload・履歴構成を同じ採用条件へ拘束する。"""
    descriptor = _descriptor()
    history_axis = next(
        axis
        for axis in descriptor["stateTransitionAxes"]
        if axis["axisId"] == "history.composition"
    )
    history_axis["conditionalValues"].pop()
    _with_digest(descriptor)

    with pytest.raises(checker.DescriptorCheckError, match="FR-040採用条件が一致しない"):
        _validate(descriptor)


def test_fr040_payload_variant_is_checked_structurally_not_by_text_search() -> None:
    """実variantを消して説明文だけにstate-correctionを残す迂回を拒否する。"""
    descriptor = _descriptor()
    payload_axis = next(
        axis
        for axis in descriptor["stateTransitionAxes"]
        if axis["axisId"] == "event.operationPayload"
    )
    capability = payload_axis["representationCapability"]
    capability["variantTags"].remove("state-correction")
    capability["description"] = "state-correction は説明文にだけ残っている"
    _with_digest(descriptor)

    with pytest.raises(
        checker.DescriptorCheckError,
        match="表現能力のvariantTagsがexact-set不一致: event.operationPayload",
    ):
        _validate(descriptor)


def test_every_input_axis_generates_coverage_obligations() -> None:
    """理由だけのnon-finite軸を許さず全入力軸からcoverage座標を生成する。"""
    descriptor = _descriptor()

    assert all(
        checker.coverage_obligation_count(axis) > 0
        for collection_name in ("stateTransitionAxes", "gameEndAxes")
        for axis in descriptor[collection_name]
    )

    zero_coverage = copy.deepcopy(descriptor)
    inning_axis = next(
        axis
        for axis in zero_coverage["stateTransitionAxes"]
        if axis["axisId"] == "state.inning"
    )
    inning_axis.pop("boundaryValues")
    inning_axis["classification"] = "non-finite"
    inning_axis["nonFiniteReason"] = "上限がない"
    _with_digest(zero_coverage)

    with pytest.raises(checker.DescriptorCheckError, match="coverage義務が0件"):
        _validate(zero_coverage)


def test_per_pitch_result_values_match_the_legacy_ui_vocabulary_evidence() -> None:
    """付録D-4が指定する旧UI由来の打撃結果33値とexact-set一致する。"""
    descriptor = _descriptor()
    result_axis = next(
        axis
        for axis in descriptor["stateTransitionAxes"]
        if axis["axisId"] == "event.perPitch.resultId"
    )
    evidence_lines = LEGACY_DATA_LAYER_PATH.read_text(encoding="utf-8").splitlines()
    batting_line = next(line for line in evidence_lines if line.startswith("| 45 |"))
    secondary_line = next(line for line in evidence_lines if line.startswith("| 46 |"))
    batting_values = re.findall(r'"([^"]+)"', batting_line)
    secondary_values = [
        value for value in re.findall(r'"([^"]+)"', secondary_line) if value != "0"
    ]

    assert len(batting_values) == 26
    assert len(secondary_values) == 7
    assert len(result_axis["values"]) == 33
    assert set(result_axis["values"]) == set(batting_values + secondary_values)


def test_unknown_source_clause_id_is_red() -> None:
    """文字列形式が妥当でも正本に実在しない由来条文IDを拒否する。"""
    descriptor = _descriptor()
    descriptor["stateTransitionAxes"].append(
        {
            "axisId": "negative.unknownSource",
            "sourceClauseId": "req:FR-999",
            "classification": "finite-enumerable",
            "values": [False, True],
        }
    )
    _with_digest(descriptor)

    with pytest.raises(checker.DescriptorCheckError, match="由来条文IDが正本に実在しない"):
        _validate(descriptor)


def test_missing_source_clause_id_is_red() -> None:
    """由来条文IDを持たない軸を閉じたschemaで拒否する。"""
    descriptor = _descriptor()
    descriptor["stateTransitionAxes"].append(
        {
            "axisId": "negative.missingSource",
            "classification": "finite-enumerable",
            "values": [False, True],
        }
    )
    _with_digest(descriptor)

    with pytest.raises(checker.DescriptorCheckError, match="oneOfに一意に一致しない"):
        _validate(descriptor)


def test_game_end_axes_match_d11_inventory_boundaries_and_sources() -> None:
    """D-11の終了判定4軸を安全範囲・正負の境界値とともに収容する。"""
    descriptor = _descriptor()
    axes = {axis["axisId"]: axis for axis in descriptor["gameEndAxes"]}

    assert {
        axis_id: (
            axis["sourceClauseId"],
            axis["ruleFieldId"],
            axis["classification"],
        )
        for axis_id, axis in axes.items()
    } == {
        "gameEnd.regulationInnings": (
            "req:F-1",
            "regulationInnings",
            "boundary-partition",
        ),
        "gameEnd.coldConditions": (
            "req:F-1",
            "coldConditions",
            "boundary-partition",
        ),
        "gameEnd.extensionLimit": (
            "req:F-1",
            "extensionLimit",
            "boundary-partition",
        ),
        "gameEnd.tiebreak": ("req:F-1", "tiebreak", "boundary-partition"),
    }
    assert all(
        source_id in SOURCE_CLAUSE_IDS
        for axis in axes.values()
        for source_id in [axis["sourceClauseId"], *axis["supportingClauseIds"]]
    )
    assert all(
        "adr:D-11" in axis["supportingClauseIds"] for axis in axes.values()
    )
    assert axes["gameEnd.regulationInnings"]["coverageBounds"] == [
        {"dimension": "innings", "minimum": 1, "maximum": 99}
    ]
    assert axes["gameEnd.regulationInnings"]["boundaryValues"] == [1, 5, 7, 9, 99]
    assert axes["gameEnd.regulationInnings"]["invalidBoundaryValues"] == [0, 100]
    assert axes["gameEnd.coldConditions"]["coverageBounds"] == [
        {"dimension": "pointDifference", "minimum": 1, "maximum": 99},
        {"dimension": "startInning", "minimum": 1, "maximum": 99},
        {"dimension": "tierCount", "minimum": 0, "maximum": 16},
    ]
    assert axes["gameEnd.coldConditions"]["boundaryValues"] == [
        "tier-count:0",
        "tier-count:1",
        "tier-count:16",
        "point-difference:1",
        "point-difference:M-1",
        "point-difference:M",
        "point-difference:M+1",
        "point-difference:99",
        "start-inning:1",
        "start-inning:N-1",
        "start-inning:N",
        "start-inning:N+1",
        "start-inning:99",
    ]
    assert axes["gameEnd.coldConditions"]["invalidBoundaryValues"] == [
        "tier-count:17",
        "point-difference:0",
        "point-difference:100",
        "start-inning:0",
        "start-inning:100",
    ]
    assert axes["gameEnd.extensionLimit"]["boundaryValues"] == [
        "none",
        "finite:R",
        "finite:R+1",
        "finite:99",
    ]
    assert axes["gameEnd.extensionLimit"]["invalidBoundaryValues"] == [
        "finite:R-1",
        "finite:100",
    ]
    assert axes["gameEnd.tiebreak"]["boundaryValues"] == [
        "none",
        "start:R+1",
        "start:L",
        "start:99",
    ]
    assert axes["gameEnd.tiebreak"]["invalidBoundaryValues"] == [
        "start:R",
        "start:L+1-when-finite",
        "start:100",
    ]


def test_cold_start_inning_r_plus_one_is_not_an_invalid_boundary() -> None:
    """条文根拠のないNとRの比較をコールド条件へ持ち込ませない。"""
    descriptor = _descriptor()
    axis = next(
        item
        for item in descriptor["gameEndAxes"]
        if item["axisId"] == "gameEnd.coldConditions"
    )
    axis["invalidBoundaryValues"].append("start-inning:R+1")
    _with_digest(descriptor)

    with pytest.raises(
        checker.DescriptorCheckError,
        match=r"条文根拠のない不正境界値.*start-inning:R\+1",
    ):
        _validate(descriptor)


def test_f1_rule_fields_have_exactly_one_top_level_coverage_owner() -> None:
    """F-1の5フィールドをcoverage4軸または非coverage1件へ一意に帰属させる。"""
    descriptor = _descriptor()
    coverage_fields = {
        axis["ruleFieldId"] for axis in descriptor["gameEndAxes"]
    }
    non_coverage_fields = {
        field["fieldId"] for field in descriptor["nonCoverageFields"]
    }
    top_level_non_coverage = {
        field_id for field_id in non_coverage_fields if "." not in field_id
    }

    assert coverage_fields == {
        "regulationInnings",
        "coldConditions",
        "extensionLimit",
        "tiebreak",
    }
    assert non_coverage_fields == _criteria().non_coverage_fields
    assert coverage_fields.isdisjoint(top_level_non_coverage)
    assert coverage_fields | top_level_non_coverage == _criteria().f1_rule_fields
    assert all(
        field["sourceClauseId"] == "req:F-1"
        and field["supportingClauseIds"] == ["adr:D-11"]
        and field["reason"]
        and field["schemaRetention"] == "required-by-projection"
        for field in descriptor["nonCoverageFields"]
    )

    duplicate_owner = copy.deepcopy(descriptor)
    duplicate_owner["gameEndAxes"][0]["ruleFieldId"] = "dh"
    _with_digest(duplicate_owner)
    with pytest.raises(
        checker.DescriptorCheckError,
        match="4軸またはF-1フィールド帰属がexact-set不一致",
    ):
        _validate(duplicate_owner)


def test_game_end_combination_rules_are_pairwise_and_full_cross_product() -> None:
    """規則フィールド間をペアワイズ、各境界と全状態・イベントを直積する。"""
    descriptor = _descriptor()

    assert descriptor["gameEndCombinationRules"] == {
        "sourceClauseId": "adr:D-11",
        "ruleFieldCombination": "pairwise-all-game-end-axes",
        "boundaryValueCombination": (
            "full-cross-product-with-all-state-and-event-axes"
        ),
    }
    assert "adr:D-11" in SOURCE_CLAUSE_IDS


def test_draw03_valid_and_invalid_tiebreak_boundaries_are_explicit() -> None:
    """DRAW-03のR < 発動回かつ有限L以下を正負の境界で固定する。"""
    descriptor = _descriptor()
    axis = next(
        axis
        for axis in descriptor["gameEndAxes"]
        if axis["axisId"] == "gameEnd.tiebreak"
    )

    assert {"none", "start:R+1", "start:L"} <= set(axis["boundaryValues"])
    assert {"start:R", "start:L+1-when-finite"} <= set(
        axis["invalidBoundaryValues"]
    )
    assert "req:DRAW-03" in axis["supportingClauseIds"]


def test_projection_rules_cover_every_axis_and_non_coverage_field_exactly_once() -> None:
    """全軸と非coverage項目が分類一致する射影規則へ一意に帰属する。"""
    descriptor = _descriptor()
    expected_targets = {
        axis["axisId"]
        for collection_name in ("stateTransitionAxes", "gameEndAxes")
        for axis in descriptor[collection_name]
    } | {field["fieldId"] for field in descriptor["nonCoverageFields"]}
    projected_targets = [
        target_id
        for rule in descriptor["projectionRules"]
        if rule["sourceKind"] != "descriptor-identity"
        for target_id in rule["targetIds"]
    ]

    assert len(projected_targets) == len(set(projected_targets))
    assert set(projected_targets) == expected_targets
    assert all(
        rule["verificationStage"] == "stage2-descriptorParity"
        and rule["mismatchAction"] == "manifest-registration-denied"
        and rule["undecidableAction"] == "fail"
        for rule in descriptor["projectionRules"]
    )


def test_projection_modes_preserve_descriptor_semantics() -> None:
    """列挙・境界・非有限・非coverageを縮小せずschema表現へ対応づける。"""
    descriptor = _descriptor()
    rules = {rule["ruleId"]: rule for rule in descriptor["projectionRules"]}

    assert rules["projection.finiteEnumerable"]["projectionMode"] == "exact-enum"
    assert "enum" in rules["projection.finiteEnumerable"]["jsonSchemaKeywords"]
    assert (
        rules["projection.boundaryPartition"]["projectionMode"]
        == "boundary-annotations"
    )
    assert "enum" not in rules["projection.boundaryPartition"]["jsonSchemaKeywords"]
    assert (
        rules["projection.structuredBoundaryPartition"]["targetIds"]
        == ["event.perPitch.thirdOutTimingByRunner"]
    )
    assert (
        rules["projection.deferredStructuredBoundaryPartition"]["projectionMode"]
        == "deferred-structured-boundary-annotations"
    )
    assert {
        "x-pitchlog-representation-capability",
        "x-pitchlog-stage2-external-constraints",
    } <= set(
        rules["projection.deferredStructuredBoundaryPartition"][
            "jsonSchemaKeywords"
        ]
    )
    assert (
        rules["projection.boundedBoundaryPartition"]["projectionMode"]
        == "bounded-boundary-annotations"
    )
    assert {"minimum", "maximum"} <= set(
        rules["projection.boundedBoundaryPartition"]["jsonSchemaKeywords"]
    )
    assert rules["projection.nonFinite"]["targetIds"] == []
    assert (
        rules["projection.nonFinite"]["projectionMode"]
        == "open-domain-with-reason"
    )
    assert "x-pitchlog-non-finite-reason" in rules["projection.nonFinite"][
        "jsonSchemaKeywords"
    ]
    assert (
        rules["projection.nonCoverageField"]["projectionMode"]
        == "required-schema-property"
    )
    assert {"properties", "required"} <= set(
        rules["projection.nonCoverageField"]["jsonSchemaKeywords"]
    )


def test_descriptor_identity_binding_is_exact_and_blocks_manifest_registration() -> None:
    """派生schemaがdescriptorId・version・digestを完全一致で参照する条件を持つ。"""
    descriptor = _descriptor()
    rule = next(
        rule
        for rule in descriptor["projectionRules"]
        if rule["sourceKind"] == "descriptor-identity"
    )

    assert set(rule["targetIds"]) == {"descriptorId", "version", "digest"}
    assert rule["parityChecks"] == [
        "descriptor-identity-exact",
        "no-extra-or-missing-targets",
    ]
    assert rule["mismatchAction"] == "manifest-registration-denied"


def test_uncovered_axis_is_undecidable_and_red() -> None:
    """射影規則から軸を1件落とすと判定不能としてfail-closedに拒否する。"""
    descriptor = _descriptor()
    rule = next(
        rule
        for rule in descriptor["projectionRules"]
        if rule["ruleId"] == "projection.finiteEnumerable"
    )
    rule["targetIds"].remove("state.half")
    _with_digest(descriptor)

    with pytest.raises(
        checker.DescriptorCheckError,
        match="射影判定不能: .*覆い漏れ",
    ):
        _validate(descriptor)


def test_stage1_descriptor_declares_stage2_parity_without_external_dependency() -> None:
    """段階2の射影条件だけを宣言しhistory-depthや外部ファイルを参照しない。"""
    descriptor = _descriptor()
    raw_text = DESCRIPTOR_PATH.read_text(encoding="utf-8")

    assert descriptor["stateTransitionAxes"]
    assert len(descriptor["gameEndAxes"]) == 4
    assert len(descriptor["nonCoverageFields"]) == 3
    assert descriptor["gameEndCombinationRules"]
    assert len(descriptor["projectionRules"]) == 8
    assert descriptor["stage2ExternalConstraints"]["status"] == "deferred"
    assert descriptor["digestSpec"]["stage1ExternalReferences"] == "forbidden"
    assert set(checker.SOURCE_CLAUSE_PATHS) == {
        Path("docs/requirements/requirements-pitchlog-2026-07-22.md"),
        Path("docs/adr/ADR-003-domain-calc-method.md"),
    }
    assert "history-depth.json" not in raw_text
    assert "主要フラグ" not in raw_text
