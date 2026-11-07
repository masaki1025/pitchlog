"""走者操作の原値閉型/metadataの作者候補。独立意味導出ではない。"""

import copy
import json
from pathlib import Path

import pytest

from pitchlog.domainrt.lineup_play_prefix_continuation import (
    LineupPrefixProtocolError,
    RunnerEventT1Input,
    RunnerValue,
    decode_lineup_prefix_request,
    decode_lineup_prefix_response,
    lineup_wire_head,
    seal_lineup_wire,
    verify_lineup_wire_seal,
)

_CASES = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "docs/features/mvp-runner-operations-connection/candidate-cases.json"
    ).read_text()
)["cases"]


def _success(wire):
    """作者の固定成功行だけを型で絞る。偽成功を生成しない。"""
    result = decode_lineup_prefix_response(json.dumps(wire))
    assert result.ok is True
    return result


@pytest.mark.parametrize("case", _CASES)
def test_original_closed_wire_round_trip_and_seal(case):
    """原値を変更せず、真正性と別の構造検査/全値digestを固定する。"""
    request = decode_lineup_prefix_request(json.dumps(case["request"]))
    response = _success(case["expected"])
    assert type(request.t1) is RunnerEventT1Input
    assert type(response.value) is RunnerValue
    assert (
        request.model_dump(mode="json", by_alias=True, exclude_unset=True)
        == case["request"]
    )
    assert (
        response.model_dump(mode="json", by_alias=True, exclude_unset=True)
        == case["expected"]
    )
    head = lineup_wire_head(request, response)
    assert head["runnerObservation"] == case["request"]["t1"]["runnerObservation"]
    assert head["runnerScoreEffects"] == case["expected"]["value"]["runnerScoreEffects"]
    sealed_request, sealed_response = seal_lineup_wire(request, response)
    verify_lineup_wire_seal(sealed_request, sealed_response)


@pytest.mark.parametrize(
    "target", ["extra", "wrong-id", "null-result", "legacy-rbi", "missing-perpitch"]
)
def test_input_never_repairs_original_wire(target):
    """余剰/欠落/型変換を原値に対して補修しない。"""
    wire = copy.deepcopy(_CASES[0]["request"])
    o = wire["t1"]["runnerObservation"]
    if target == "extra":
        o["perPitch"]["extra"] = True
    elif target == "wrong-id":
        o["perPitch"]["resultId"] = "strategy-category.steal"
    elif target == "null-result":
        o["perPitch"]["runnerEventPayload"]["by_runner"]["first"] = None
    elif target == "legacy-rbi":
        o["perPitch"]["rbi"]["cause_by_runner"] = "not-required"
    else:
        del o["perPitch"]
    before = copy.deepcopy(wire)
    with pytest.raises(LineupPrefixProtocolError):
        decode_lineup_prefix_request(json.dumps(wire))
    assert wire == before


def test_observation_and_score_evidence_cannot_change_after_seal():
    """原因/有効得点根拠を32field外へ捨てず、新variantだけに束縛する。"""
    case = _CASES[3]
    request, response = seal_lineup_wire(
        decode_lineup_prefix_request(json.dumps(case["request"])),
        _success(case["expected"]),
    )
    for target in ("observation", "evidence"):
        q = request.model_dump(mode="json", by_alias=True, exclude_unset=True)
        r = response.model_dump(mode="json", by_alias=True, exclude_unset=True)
        if target == "observation":
            q["t1"]["runnerObservation"]["primaryResultId"] = "batting-result.foul"
        else:
            r["value"]["runnerScoreEffects"][0]["validRun"] = False
        with pytest.raises(LineupPrefixProtocolError):
            verify_lineup_wire_seal(
                decode_lineup_prefix_request(json.dumps(q)),
                _success(r),
            )


@pytest.mark.parametrize("case", _CASES)
def test_original_out_cause_and_actual_advance_are_physical_values(case):
    """唯一核の起点out/到達と原観測原因を10物理列へ写す。"""
    from uuid import UUID

    from pitchlog.domainrt.lineup_prefix_source import _validate_runner_projection
    from pitchlog.sync.terminal_pitch_projection import runner_physical_rows

    request = decode_lineup_prefix_request(json.dumps(case["request"]))
    response = _success(case["expected"])
    _validate_runner_projection(request, response)
    rows = runner_physical_rows(
        request.source.runners,
        t1=response.value.t1,
        t1_input=request.t1,
        tenant_id=UUID(request.prefix_ref.tenant_id),
        play_id=UUID(request.play_identity.play_id),
    )
    assert isinstance(request.t1, RunnerEventT1Input)
    p = request.t1.runner_observation.per_pitch
    outcomes = getattr(p.runner_event_payload, "by_runner", None) or getattr(
        p.runner_advance_overrides, "by_runner", None
    )
    assert outcomes is not None
    labels = {"pitcher-pickoff-out": "投手牽制死", "caught-stealing": "盗塁死"}
    for row, source in zip(rows, request.source.runners, strict=True):
        observed = getattr(
            outcomes, {"1": "first", "2": "second", "3": "third"}[source.base]
        )
        assert row["runner_id"] == source.runner_id
        assert row["responsible_pitcher_id"] == source.responsible_pitcher_id
        if observed.kind == "out":
            assert row["status"] == labels[observed.out_kind]
        else:
            assert (
                row["status"]
                == {"second": "二進", "third": "三進", "home": "本進"}[
                    observed.destination
                ]
            )
        assert row["status_source"] == "manual"
    if rows:
        raw = copy.deepcopy(case["request"])
        by = raw["t1"]["runnerObservation"]["perPitch"]
        outcomes = (
            by["runnerEventPayload"].get("by_runner")
            or by["runnerAdvanceOverridesByRunner"]["by_runner"]
        )
        outcomes["first"]["runner"]["player_id"] = (
            "10000000-0000-0000-0000-000000000288"
        )
        bad = decode_lineup_prefix_request(json.dumps(raw))
        with pytest.raises(Exception) as caught:
            runner_physical_rows(
                request.source.runners,
                t1=response.value.t1,
                t1_input=bad.t1,
                tenant_id=UUID(request.prefix_ref.tenant_id),
                play_id=UUID(request.play_identity.play_id),
            )
        assert type(caught.value).__name__ == "OrdinaryPitchExecutionError"


def _payload(case):
    """固定数学候補に明示された実観測を付ける。実認可/実保存の証拠ではない。"""
    from pitchlog.sync.terminal_pitch_payload import LineupPitchCalculation

    request, response = seal_lineup_wire(
        decode_lineup_prefix_request(json.dumps(case["request"])),
        _success(case["expected"]),
    )
    calculation = LineupPitchCalculation.model_validate_json(
        json.dumps(
            {
                "formatVersion": "play-prefix-calculation-v3",
                "artifactSha256": request.source.execution_artifact_sha256,
                "request": request.model_dump(
                    mode="json", by_alias=True, exclude_unset=True
                ),
                "response": response.model_dump(
                    mode="json", by_alias=True, exclude_unset=True
                ),
            }
        )
    )
    observed = {
        "runnerObservation": copy.deepcopy(case["request"]["t1"]["runnerObservation"])
    }
    if request.t1.pitch_event_kind == "pitch-event":
        observed.update(
            {
                "pitchTypeKey": "pitch-type.straight",
                "course": {"unit": "1/263", "x": "131", "y": "132"},
                "pitchSpeed": {"kmh": None, "outsideRangeConfirmed": False},
                "stance": None,
                "battingSide": None,
            }
        )
    else:
        observed["kind"] = "non-pitch-event"
    payload = {
        "formatVersion": "play-prefix-play-v3",
        "observations": observed,
        "participants": copy.deepcopy(case["expected"]["value"]["beforeParticipants"]),
        "calculation": calculation.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        ),
    }
    return payload, calculation


@pytest.mark.parametrize("case", _CASES)
def test_same_v7_original_physical_41_and_t5_generated(case):
    """同原値V7/全41列/単一生成T5を接続し、偽認可や成功を生成しない。"""
    from uuid import UUID

    from pitchlog.stats.facts import evaluate_native_projection, native_projection
    from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
    from pitchlog.sync.terminal_pitch_payload import read_lineup_pitch_payload

    payload, calculation = _payload(case)
    difference = payload["calculation"]["response"]["value"]["newHistoryEntry"][
        "difference"
    ]
    checked = read_lineup_pitch_payload(
        json.dumps(payload), json.dumps(difference), expected_calculation=calculation
    )
    assert checked.model_dump(mode="json", by_alias=True, exclude_unset=True) == payload
    q = calculation.request
    row = pitch_physical_row(
        checked.observations,
        checked.participants,
        q.t1.result_id,
        tenant_id=UUID(q.prefix_ref.tenant_id),
        game_id=UUID(q.prefix_ref.game_id),
        source_event_id=UUID(q.play_identity.event_id),
        row_id=UUID(q.play_identity.play_id),
        play_number=1,
    )
    assert row["event_kind"] == (
        "pitch" if q.t1.pitch_event_kind == "pitch-event" else "non_pitch"
    )
    assert (row["course_x"] is None) == (row["event_kind"] == "non_pitch")
    projection = native_projection(
        payload, source_event_id=UUID(q.play_identity.event_id)
    )
    assert projection["completeness"]["steals"] == "complete"
    assert projection["completeness"]["runs_rbi"] == "complete"
    result = evaluate_native_projection(
        payload, source_event_id=UUID(q.play_identity.event_id)
    )
    assert result["metrics"]["stolen_bases"]["state"] == "available"


@pytest.mark.parametrize(
    ("index", "pitch", "outs", "runs", "steals", "strikeouts"),
    [
        (0, "0", "1", "0", "0", "0"),
        (1, "0", "1", "0", "0", "0"),
        (2, "1", "2", "0", "0", "1"),
        (3, "1", "0", "1", "0", "0"),
        (4, "1", "0", "1", "0", "0"),
        (5, "0", "0", "1", "0", "0"),
        (6, "1", "0", "0", "1", "0"),
    ],
)
def test_generated_t5_counts_and_credit_id(
    index, pitch, outs, runs, steals, strikeouts
):
    """新規の数式を作らず、生成核の実値と帰属を明示期待へ照合する。"""
    from uuid import UUID

    from pitchlog.stats.facts import evaluate_native_projection, native_projection

    payload, calculation = _payload(_CASES[index])
    event_id = UUID(calculation.request.play_identity.event_id)
    result = evaluate_native_projection(payload, source_event_id=event_id)["metrics"]
    for name, expected in (
        ("pitch_count", pitch),
        ("pitching_outs", outs),
        ("runs", runs),
        ("rbi", "0"),
        ("stolen_bases", steals),
        ("pitcher_k", strikeouts),
    ):
        assert result[name]["state"] == "available"
        assert result[name]["value"] == expected
    if steals == "1":
        assert result["stolen_bases"]["credits"] == [
            {
                "player_id": calculation.request.source.runners[0].runner_id,
                "quantity": "1",
            }
        ]
    invalid = copy.deepcopy(payload)
    invalid["observations"]["runnerObservation"]["perPitch"]["extra"] = True
    with pytest.raises(ValueError):
        native_projection(invalid, source_event_id=event_id)
