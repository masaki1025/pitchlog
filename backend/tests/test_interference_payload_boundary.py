"""妨害V7の原裁定と旧打球との分離を検証する。"""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator

from pitchlog.domainrt.lineup_play_prefix_continuation import (
    AdjudicatedInterferenceT1Input,
    BattingInterferencePenaltyT1Input,
    BattingInterferencePlayT1Input,
    LineupPrefixProtocolError,
    LineupPrefixRequest,
    LineupPrefixSuccess,
    Runner,
    lineup_wire_head,
)
from pitchlog.domainrt.lineup_prefix_source import (
    require_batted_hit_observations,
    require_interference_observations,
)
from pitchlog.sync.ordinary_pitch_payload import OrdinaryPitchParticipants
from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
from pitchlog.sync.terminal_pitch_payload import (
    AdjudicatedInterferenceObservations,
    BattedHitPlayObservations,
    BattingInterferencePenaltyObservations,
    BattingInterferencePlayObservations,
    LineupPitchPlayPayload,
)
from pitchlog.sync.terminal_pitch_projection import runner_physical_rows

ROOT = Path(__file__).resolve().parents[2]
BASE = json.loads(
    (ROOT / "contracts/state-transition/batted_hit_prefix_cases_v1.json").read_text()
)["cases"][0]["request"]
PITCH = {
    "pitchTypeKey": "fixture.fastball",
    "course": {"unit": "1/263", "x": "132", "y": "131"},
    "pitchSpeed": {"kmh": None, "outsideRangeConfirmed": False},
    "stance": None,
    "battingSide": None,
}


def _penalty() -> BattingInterferencePenaltyT1Input:
    """旧打球fixtureのsourceを使い、裁定だけを閉入力へ変更する。"""
    wire = copy.deepcopy(BASE)
    wire["t1"].update(
        eventKind="secondary-result",
        resultId="secondary-result.batting-interference",
        interferenceRuling={
            "kind": "batting-interference",
            "adopted": {"kind": "penalty-award"},
            "third_base_scoring_attempt": {"kind": "not-required"},
        },
    )
    t1 = LineupPrefixRequest.model_validate_json(json.dumps(wire)).t1
    assert type(t1) is BattingInterferencePenaltyT1Input
    return t1


def test_penalty_v7_requires_exact_original_ruling():
    """結果IDだけでは妨害原本とならず、別裁定を同T1へ混ぜない。"""
    t1 = _penalty()
    raw = {
        **PITCH,
        "resultId": "secondary-result.batting-interference",
        "interferenceRuling": t1.interference_ruling.model_dump(
            mode="json", by_alias=True
        ),
    }
    observed = BattingInterferencePenaltyObservations.model_validate_json(
        json.dumps(raw)
    )
    require_interference_observations(t1, observed)
    for field, value in [
        ("resultId", "secondary-result.obstruction"),
        (
            "interferenceRuling",
            {
                "kind": "batting-interference",
                "adopted": {"kind": "play-result", "resultId": "batting-result.single"},
                "third_base_scoring_attempt": {"kind": "not-required"},
            },
        ),
    ]:
        changed = {**raw, field: value}
        with pytest.raises(ValueError):
            observed = BattingInterferencePenaltyObservations.model_validate_json(
                json.dumps(changed)
            )
            require_interference_observations(t1, observed)
    with pytest.raises(ValueError):
        BattedHitPlayObservations.model_validate_json(json.dumps(raw))


def test_interference_wire_head_is_closed_without_changing_old_heads():
    """旧head全件と妨害の原裁定・算入根拠を別variantへ閉じる。"""
    schema_path = ROOT / "contracts/state-transition/lineup_play_prefix_schema_v1.json"
    schema = json.loads(schema_path.read_text())
    validator = Draft202012Validator(
        {"$defs": schema["$defs"], "$ref": "#/$defs/WireHead"}
    )
    old_path = (
        ROOT / "contracts/state-transition/lineup_play_prefix_payload_vectors_v1.json"
    )
    old_rows = json.loads(old_path.read_text())["cases"]
    assert len(old_rows) == 34
    assert all(validator.is_valid(row["wireHead"]) for row in old_rows)
    head = copy.deepcopy(old_rows[0]["wireHead"])
    head["interferenceRuling"] = _penalty().interference_ruling.model_dump(
        mode="json", by_alias=True
    )
    head["runnerScoreEffects"] = []
    assert validator.is_valid(head)
    for changed in (
        {**head, "runnerScoreEffects": None},
        {**head, "rbiRulingByRunner": {"1": "ordinary-play"}},
        {**head, "unknown": True},
    ):
        assert not validator.is_valid(changed)
    interference_validator = Draft202012Validator(
        {"$defs": schema["$defs"], "$ref": "#/$defs/InterferenceNoRbiWireHead"}
    )
    assert not interference_validator.is_valid(
        {k: v for k, v in head.items() if k != "interferenceRuling"}
    )
    play = copy.deepcopy(head)
    play["interferenceRuling"]["adopted"] = {
        "kind": "play-result", "resultId": "batting-result.single",
    }
    play["rbiRulingByRunner"] = {"1": "ordinary-play"}
    assert validator.is_valid(play)
    batter_id = BASE["source"]["participants"]["batterId"]
    person = {
        "kind": "batter",
        "batter_id": {"kind": "official", "player_id": batter_id},
    }
    obstruction = copy.deepcopy(head)
    obstruction["interferenceRuling"] = {
        "kind": "obstruction", "play_kind": "play-on-obstructed-runner",
        "obstructed": person,
        "awarded_destinations": [{"person": person, "destination": "first"}],
        "out_targets": [], "batter_before_first": True,
    }
    assert validator.is_valid(obstruction)
    assert not validator.is_valid(
        {**obstruction, "rbiRulingByRunner": {"1": "ordinary-play"}}
    )


def test_interference_wire_head_binds_original_ruling_and_typed_effects():
    """新裁定のheadを旧応答型へ落とさず原要求から封印する。"""
    case_path = ROOT / "contracts/state-transition/batted_hit_prefix_cases_v1.json"
    case = json.loads(case_path.read_text())["cases"][0]
    request = copy.deepcopy(case["request"])
    request["t1"].update(
        eventKind="secondary-result",
        resultId="secondary-result.batting-interference",
        interferenceRuling={
            "kind": "batting-interference",
            "adopted": {"kind": "penalty-award"},
            "third_base_scoring_attempt": {"kind": "not-required"},
        },
    )
    response = copy.deepcopy(case["expected"])
    response["value"]["runnerScoreEffects"] = []
    q = LineupPrefixRequest.model_validate_json(json.dumps(request))
    r = LineupPrefixSuccess.model_validate_json(json.dumps(response))
    head = lineup_wire_head(q, r)
    assert head["interferenceRuling"] == request["t1"]["interferenceRuling"]
    assert head["runnerScoreEffects"] == []
    assert "rbiRulingByRunner" not in head
    del response["value"]["runnerScoreEffects"]
    old_value = LineupPrefixSuccess.model_validate_json(json.dumps(response))
    with pytest.raises(LineupPrefixProtocolError):
        lineup_wire_head(q, old_value)


def test_obstruction_v7_does_not_accept_an_unmatched_ref_or_unknown_field():
    """裁定参照を同sourceへ束縛し、V7への余剰値を拒否する。"""
    wire = copy.deepcopy(BASE)
    batter = wire["source"]["participants"]["batterId"]
    person = {"kind": "batter", "batter_id": {"kind": "official", "player_id": batter}}
    wire["t1"] = {
        "eventKind": "secondary-result",
        "resultId": "secondary-result.obstruction",
        "pitchEventKind": "pitch-event",
        "before": wire["t1"]["before"],
        "interferenceRuling": {
            "kind": "obstruction",
            "play_kind": "play-on-obstructed-runner",
            "obstructed": person,
            "awarded_destinations": [{"person": person, "destination": "first"}],
            "out_targets": [],
            "batter_before_first": True,
        },
    }
    t1 = LineupPrefixRequest.model_validate_json(json.dumps(wire)).t1
    assert type(t1) is AdjudicatedInterferenceT1Input
    raw = {
        **PITCH,
        "resultId": "secondary-result.obstruction",
        "interferenceRuling": t1.interference_ruling.model_dump(
            mode="json", by_alias=True
        ),
    }
    observed = AdjudicatedInterferenceObservations.model_validate_json(json.dumps(raw))
    require_interference_observations(t1, observed)
    for changed in [
        {**raw, "unknown": True},
        {
            **raw,
            "interferenceRuling": {
                **raw["interferenceRuling"],
                "out_targets": [person],
            },
        },
    ]:
        with pytest.raises(ValueError):
            candidate = AdjudicatedInterferenceObservations.model_validate_json(
                json.dumps(changed)
            )
            require_interference_observations(t1, candidate)


def test_penalty_physical_row_preserves_secondary_result_without_inventing_main():
    """妨害の主結果を仮造せず、観測された副結果だけを41列へ写す。"""
    t1 = _penalty()
    observed = BattingInterferencePenaltyObservations.model_validate_json(
        json.dumps(
            {
                **PITCH,
                "resultId": t1.result_id,
                "interferenceRuling": t1.interference_ruling.model_dump(
                    mode="json", by_alias=True
                ),
            }
        )
    )
    people = OrdinaryPitchParticipants.model_validate_json(
        json.dumps(BASE["source"]["participants"])
    )
    uid = UUID(BASE["prefixRef"]["tenantId"])
    row = pitch_physical_row(
        observed,
        people,
        t1.result_id,
        tenant_id=uid,
        game_id=UUID(BASE["prefixRef"]["gameId"]),
        source_event_id=uid,
        row_id=uid,
        play_number=1,
    )
    assert row["batting_result_key"] is None
    assert row["secondary_batting_result_key"] == t1.result_id
    assert row["event_kind"] == "pitch"
    with pytest.raises(ValueError):
        pitch_physical_row(
            observed,
            people,
            "secondary-result.obstruction",
            tenant_id=uid,
            game_id=uid,
            source_event_id=uid,
            row_id=uid,
            play_number=1,
        )


def test_v7_union_selects_penalty_without_falling_into_old_pitch():
    """新裁定のV7全観測を旧通常投球の部分集合へ読み替えない。"""
    source = ROOT / "contracts/state-transition/batted_hit_prefix_cases_v1.json"
    case = json.loads(source.read_text())["cases"][0]
    t1 = _penalty()
    raw = {
        "formatVersion": "play-prefix-play-v3",
        "observations": {
            **PITCH,
            "resultId": t1.result_id,
            "interferenceRuling": t1.interference_ruling.model_dump(
                mode="json", by_alias=True
            ),
        },
        "participants": case["expected"]["value"]["beforeParticipants"],
        "calculation": {
            "formatVersion": "play-prefix-calculation-v3",
            "artifactSha256": case["request"]["source"]["executionArtifactSha256"],
            "request": case["request"],
            "response": case["expected"],
        },
    }
    parsed = LineupPitchPlayPayload.model_validate_json(json.dumps(raw))
    assert type(parsed.observations) is BattingInterferencePenaltyObservations
    assert parsed.model_dump(mode="json", by_alias=True, exclude_unset=True) == raw
    del raw["observations"]["interferenceRuling"]
    with pytest.raises(ValueError):
        LineupPitchPlayPayload.model_validate_json(json.dumps(raw))


def test_adopted_play_keeps_batted_fields_and_the_actual_selected_result():
    """実プレイ採用でも旧打球原観測を落とさず裁定だけ追加する。"""
    wire = copy.deepcopy(BASE)
    selected = wire["t1"]["resultId"]
    ruling = {
        "kind": "batting-interference",
        "adopted": {"kind": "play-result", "resultId": selected},
        "third_base_scoring_attempt": {"kind": "not-required"},
    }
    wire["t1"]["interferenceRuling"] = ruling
    t1 = LineupPrefixRequest.model_validate_json(json.dumps(wire)).t1
    assert type(t1) is BattingInterferencePlayT1Input
    observed = {
        **PITCH,
        "resultId": selected,
        "battedBall": {
            "typeKey": None,
            "strengthKey": None,
            "hitX": None,
            "hitY": None,
            "rawFielderPosition": None,
            "resolvedFielderId": None,
        },
        "officialScoringPayload": {
            "kind": "no-error",
            "errorCount": "0",
            "fielders": [],
        },
        "interferenceRuling": ruling,
        "runnerAdvanceOverridesByRunner": {"kind": "not-applied", "overrides": []},
        "thirdOutObservation": {"kind": "none"},
        "thirdOutTimingByRunner": {},
    }
    parsed = BattingInterferencePlayObservations.model_validate_json(
        json.dumps(observed)
    )
    require_batted_hit_observations(t1, parsed)
    with pytest.raises(ValueError):
        BattedHitPlayObservations.model_validate_json(json.dumps(observed))
    changed = {**observed, "resultId": "batting-result.double"}
    with pytest.raises(ValueError):
        parsed = BattingInterferencePlayObservations.model_validate_json(
            json.dumps(changed)
        )
        require_batted_hit_observations(t1, parsed)


def test_penalty_physical_runner_status_distinguishes_force_and_observed_attempt():
    """物理投影だけを検査する。入力T1は実host成功資格ではない。"""
    t1 = _penalty()
    ruling = t1.model_dump(mode="json", by_alias=True, exclude_unset=True)
    ruling["interferenceRuling"]["third_base_scoring_attempt"] = {
        "kind": "observed",
        "value": "squeeze",
    }
    t1 = BattingInterferencePenaltyT1Input.model_validate_json(json.dumps(ruling))
    runner_ids = [
        "10000000-0000-4000-8000-000000000001",
        "10000000-0000-4000-8000-000000000003",
    ]
    before = tuple(
        Runner.model_validate_json(
            json.dumps(
                {
                    "base": base,
                    "runnerId": runner_id,
                    "responsiblePitcherId": BASE["source"]["participants"]["pitcherId"],
                    "status": "継続",
                    "statusSource": "auto",
                }
            )
        )
        for base, runner_id in zip(("1", "3"), runner_ids, strict=True)
    )
    effect = SimpleNamespace
    actual_t1 = SimpleNamespace(
        out_effect=effect(targets=()),
        runner_default_advance=effect(
            first=effect(modality="forced", destination="2"),
            second=effect(modality="not-applicable", destination=None),
            third=effect(modality="optional", destination="4"),
        ),
    )
    uid = UUID(BASE["prefixRef"]["tenantId"])
    rows = runner_physical_rows(
        before, t1=actual_t1, t1_input=t1, tenant_id=uid, play_id=uid
    )
    assert [(row["status"], row["status_source"]) for row in rows] == [
        ("二進", "auto"),
        ("本進", "manual"),
    ]
