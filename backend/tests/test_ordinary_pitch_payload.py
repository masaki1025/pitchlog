"""通常投球の全封筒codecを保存資格と混同しない。"""

import json
from pathlib import Path
from typing import Literal, cast

import pytest

from pitchlog.domainrt.ordinary_pitch_continuation import (
    OrdinaryContinuationRequest,
    OrdinaryContinuationSuccess,
    decode_ordinary_continuation_response,
)
from pitchlog.sync.first_ball_payload import FirstBallObservations
from pitchlog.sync.ordinary_pitch_payload import (
    OrdinaryPitchCalculation,
    OrdinaryPitchParticipants,
    OrdinaryPitchPayloadError,
    format_ordinary_pitch_payload,
    read_ordinary_pitch_payload,
)

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads(
    (
        ROOT / "contracts/state-transition/ordinary37_continuation_candidate_v1.json"
    ).read_text()
)["cases"]
SUCCESS = [case for case in CASES if case["expected"]["response"]["ok"]]


def _values(case):
    request = OrdinaryContinuationRequest.model_validate_json(
        json.dumps(case["request"])
    )
    response = decode_ordinary_continuation_response(
        json.dumps(case["expected"]["response"])
    )
    assert isinstance(response, OrdinaryContinuationSuccess)
    calc = OrdinaryPitchCalculation(
        formatVersion="ordinary-pitch-calculation-v1",
        artifactSha256="a" * 64,
        request=request,
        response=response,
    )
    people = OrdinaryPitchParticipants(
        batterId="11111111-0000-4000-8000-000000000001",
        pitcherId="11111111-0000-4000-8000-000000000002",
        catcherId="11111111-0000-4000-8000-000000000003",
        battingOrder=cast(
            Literal["1", "2", "3", "4", "5", "6", "7", "8", "9"],
            request.t1.before.state_fields.batting_order,
        ),
    )
    obs = FirstBallObservations.model_validate(
        {
            "pitchTypeKey": "pitch-type.straight",
            "course": {"unit": "1/263", "x": "131", "y": "132"},
            "pitchSpeed": {"kmh": None, "outsideRangeConfirmed": False},
            "stance": None,
            "battingSide": None,
        }
    )
    return obs, people, calc


@pytest.mark.parametrize("case", SUCCESS, ids=lambda case: case["caseId"])
def test_complete_payload_and_difference_match_static_math_case(case):
    """全成功caseの全request/response/差分を静的原典と比較する。"""
    obs, people, calc = _values(case)
    v7, v8 = format_ordinary_pitch_payload(obs, people, calc)
    value = read_ordinary_pitch_payload(
        v7, v8, expected_calculation=calc, expected_participants=people
    )
    assert value.model_dump(mode="json", by_alias=True, exclude_unset=True) == {
        "formatVersion": "ordinary-pitch-play-v1",
        "observations": obs.model_dump(mode="json", by_alias=True),
        "participants": people.model_dump(mode="json", by_alias=True),
        "calculation": {
            "formatVersion": "ordinary-pitch-calculation-v1",
            "artifactSha256": "a" * 64,
            "request": case["request"],
            "response": case["expected"]["response"],
        },
    }
    assert (
        json.loads(v8)
        == case["expected"]["response"]["value"]["newHistoryEntry"]["difference"]
    )


@pytest.mark.parametrize(
    "field", ["formatVersion", "observations", "participants", "calculation"]
)
def test_missing_or_extra_top_level_is_rejected(field):
    """exact4の欠落と未知keyを拒否する。"""
    obs, people, calc = _values(SUCCESS[0])
    v7, v8 = format_ordinary_pitch_payload(obs, people, calc)
    raw = json.loads(v7)
    del raw[field]
    with pytest.raises(OrdinaryPitchPayloadError):
        read_ordinary_pitch_payload(
            json.dumps(raw), v8, expected_calculation=calc, expected_participants=people
        )
    raw = json.loads(v7)
    raw["unknown"] = True
    with pytest.raises(OrdinaryPitchPayloadError):
        read_ordinary_pitch_payload(
            json.dumps(raw), v8, expected_calculation=calc, expected_participants=people
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "nan",
        "alias",
        "boolean-flag",
        "history-difference",
        "foreign-participant",
        "artifact-hash",
    ],
)
def test_boundary_mismatches_are_rejected(mutation):
    """型補修・別参加者・別artifact・別差分を拒否する。"""
    obs, people, calc = _values(SUCCESS[0])
    v7, v8 = format_ordinary_pitch_payload(obs, people, calc)
    raw = json.loads(v7)
    if mutation == "duplicate":
        v7 = '{"formatVersion":"ordinary-pitch-play-v1",' + v7[1:]
    elif mutation == "nan":
        v7 = v7.replace('"kmh":null', '"kmh":NaN')
    elif mutation == "alias":
        raw["format_version"] = raw.pop("formatVersion")
        v7 = json.dumps(raw)
    elif mutation == "boolean-flag":
        flags = raw["calculation"]["response"]["value"]["t1"]["statFlags"]
        flags[next(iter(flags))] = 1
        v7 = json.dumps(raw)
    elif mutation == "history-difference":
        diff = json.loads(v8)
        diff["unknown"] = True
        v8 = json.dumps(diff)
    elif mutation == "foreign-participant":
        raw["participants"]["pitcherId"] = "aaaaaaaa-0000-4000-8000-000000000001"
        v7 = json.dumps(raw)
    else:
        raw["calculation"]["artifactSha256"] = "b" * 64
        v7 = json.dumps(raw)
    with pytest.raises(OrdinaryPitchPayloadError):
        read_ordinary_pitch_payload(
            v7, v8, expected_calculation=calc, expected_participants=people
        )


@pytest.mark.parametrize("case", SUCCESS, ids=lambda case: case["caseId"])
def test_real_checkpoint_request_composition_preserves_model_boundaries(case):
    """Cold tuple等をJSON配列へ変えてstrict Python検証を壊さない。"""
    from types import SimpleNamespace

    from pitchlog.sync.ordinary_pitch_execution import _request_from_checkpoint

    _, _, calc = _values(case)
    original = calc.request
    doc = SimpleNamespace(
        prefix_ref=original.prefix_ref,
        rules=original.rules,
        after=original.t1.before,
        t2=original.prior.t2,
    )
    rebuilt = _request_from_checkpoint(doc, original.t1)
    assert rebuilt == original
    assert (
        json.loads(rebuilt.model_dump_json(by_alias=True, exclude_unset=True))
        == case["request"]
    )
