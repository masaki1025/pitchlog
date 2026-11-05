"""全明示観測と採用計算に一致する打球V7/V8の閉codecを照合する。"""

import copy
import json
from pathlib import Path

import pytest

from pitchlog.domainrt.lineup_play_prefix_continuation import (
    LineupPrefixRequest,
    LineupPrefixSuccess,
)
from pitchlog.domainrt.lineup_prefix_source import require_batted_hit_observations
from pitchlog.sync.first_ball_payload import FirstBallObservations
from pitchlog.sync.terminal_pitch_payload import (
    BattedHitPlayObservations,
    LineupPitchCalculation,
    TerminalPitchPayloadError,
    format_batted_hit_prefix_payload,
    read_lineup_pitch_payload,
)

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads(
    (ROOT / "contracts/state-transition/batted_hit_prefix_cases_v1.json").read_text()
)["cases"]


def observations(case):
    """結果から補完せず、fixture記録者が全明示値を提出した観測を使う。"""
    return {
        "pitchTypeKey": "fixture.fastball",
        "course": {"unit": "1/263", "x": "132", "y": "131"},
        "pitchSpeed": {"kmh": None, "outsideRangeConfirmed": False},
        "stance": None,
        "battingSide": None,
        "resultId": case["request"]["t1"]["resultId"],
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
        "interferenceRuling": {"kind": "not-required"},
        "runnerAdvanceOverridesByRunner": {"kind": "not-applied", "overrides": []},
        "thirdOutObservation": {"kind": "none"},
        "thirdOutTimingByRunner": {},
    }


def values(case):
    """独立19期待から計算封筒を組み、writer成功や資格は作らない。"""
    q = LineupPrefixRequest.model_validate_json(json.dumps(case["request"]))
    r = LineupPrefixSuccess.model_validate_json(json.dumps(case["expected"]))
    calc = LineupPitchCalculation.model_validate_json(
        json.dumps(
            {
                "formatVersion": "play-prefix-calculation-v3",
                "artifactSha256": q.source.execution_artifact_sha256,
                "request": q.model_dump(mode="json", by_alias=True, exclude_unset=True),
                "response": r.model_dump(
                    mode="json", by_alias=True, exclude_unset=True
                ),
            }
        )
    )
    return BattedHitPlayObservations.model_validate_json(
        json.dumps(observations(case))
    ), calc


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["caseId"])
def test_complete_observations_and_full_before_people_are_retained(case):
    """V7の全観測/実before投捕打者とV8の全差分を落とさず比較する。"""
    observed, calc = values(case)
    v7, v8 = format_batted_hit_prefix_payload(observed, calc)
    decoded = read_lineup_pitch_payload(v7, v8, expected_calculation=calc)
    assert json.loads(v7) == {
        "formatVersion": "play-prefix-play-v3",
        "observations": observations(case),
        "participants": case["expected"]["value"]["beforeParticipants"],
        "calculation": calc.model_dump(mode="json", by_alias=True, exclude_unset=True),
    }
    assert json.loads(v8) == case["expected"]["value"]["newHistoryEntry"]["difference"]
    assert decoded.observations.model_dump(mode="json", by_alias=True) == observations(
        case
    )
    assert (
        decoded.participants.model_dump(mode="json", by_alias=True)
        == case["expected"]["value"]["beforeParticipants"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "result",
        "scoring-kind",
        "error-count",
        "fielder",
        "interference",
        "advance",
        "third-out",
        "third-timing",
        "missing-nullable",
        "coordinate",
        "numeric-coordinate",
        "unknown",
        "legacy-observations",
        "math-unknown",
    ],
)
def test_observation_damage_never_becomes_batted_success(mutation):
    """不足観測/失策/併発/推測ID/型破損を既投球へfallbackしない。"""
    observed, calc = values(CASES[0])
    v7, v8 = format_batted_hit_prefix_payload(observed, calc)
    wire = json.loads(v7)
    data = wire["observations"]
    if mutation == "result":
        data["resultId"] = "batting-result.double"
    elif mutation == "scoring-kind":
        data["officialScoringPayload"]["kind"] = "error-recorded"
    elif mutation == "error-count":
        data["officialScoringPayload"]["errorCount"] = "1"
    elif mutation == "fielder":
        data["officialScoringPayload"]["fielders"] = [
            "10000000-0000-0000-0000-000000000001"
        ]
    elif mutation == "interference":
        data["interferenceRuling"]["kind"] = "offensive-interference"
    elif mutation == "advance":
        data["runnerAdvanceOverridesByRunner"]["overrides"] = [{"batter": "second"}]
    elif mutation == "third-out":
        data["thirdOutObservation"]["kind"] = "force"
    elif mutation == "third-timing":
        data["thirdOutTimingByRunner"]["batter"] = "home-before-third-out"
    elif mutation == "missing-nullable":
        del data["battedBall"]["hitX"]
    elif mutation == "coordinate":
        data["battedBall"]["hitX"] = "NaN"
    elif mutation == "numeric-coordinate":
        data["battedBall"]["hitX"] = 1.5
    elif mutation == "unknown":
        data["battedBall"]["unknown"] = None
    elif mutation == "math-unknown":
        wire["calculation"]["request"]["t1"]["unknown"] = True
    elif mutation == "legacy-observations":
        for key in [
            "resultId",
            "battedBall",
            "officialScoringPayload",
            "interferenceRuling",
            "runnerAdvanceOverridesByRunner",
            "thirdOutObservation",
            "thirdOutTimingByRunner",
        ]:
            del data[key]
    with pytest.raises(TerminalPitchPayloadError):
        read_lineup_pitch_payload(json.dumps(wire), v8, expected_calculation=calc)


def test_four_math_tags_without_full_observations_do_not_qualify():
    """数学入力だけが有っても元投球5観測から打球原本を補わない。"""
    _, calc = values(CASES[0])
    old = observations(CASES[0])
    for key in [
        "resultId",
        "battedBall",
        "officialScoringPayload",
        "interferenceRuling",
        "runnerAdvanceOverridesByRunner",
        "thirdOutObservation",
        "thirdOutTimingByRunner",
    ]:
        del old[key]
    with pytest.raises(ValueError):
        require_batted_hit_observations(
            calc.request.t1, FirstBallObservations.model_validate_json(json.dumps(old))
        )


def test_original_json_duplicate_nonfinite_and_unknown_remain_rejected():
    """辞書化の修復で元JSON破損を隠さない。"""
    observed, calc = values(CASES[0])
    v7, v8 = format_batted_hit_prefix_payload(observed, calc)
    wire = copy.deepcopy(json.loads(v7))
    wire["observations"]["battedBall"]["hitX"] = float("nan")
    for raw in [
        v7.replace('"pitchTypeKey":', '"pitchTypeKey":"other","pitchTypeKey":', 1),
        json.dumps(wire),
    ]:
        with pytest.raises(TerminalPitchPayloadError):
            read_lineup_pitch_payload(raw, v8, expected_calculation=calc)
