"""凡打死の実artifactと原本観測を同じv3保存境界で確認する。"""

import copy
import json
from pathlib import Path

import pytest
from domainrt.test_lineup_play_prefix_continuation import current_case

from pitchlog.domainrt.lineup_play_prefix_continuation import (
    LineupPrefixRequest,
    LineupPrefixSuccess,
    evaluate_lineup_prefix_continuation,
    seal_lineup_wire,
)
from pitchlog.domainrt.lineup_prefix_source import require_batted_hit_observations
from pitchlog.sync.terminal_pitch_payload import (
    BattedHitPlayObservations,
    LineupPitchCalculation,
    TerminalPitchPayloadError,
    format_batted_hit_prefix_payload,
    read_lineup_pitch_payload,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = json.loads(
    (ROOT / "contracts/state-transition/batted_hit_prefix_cases_v1.json").read_text()
)["cases"][0]
MATRIX = json.loads(
    (ROOT / "contracts/state-transition/state_transition_contract_v1.json").read_text()
)


def _case():
    """旧安打caseの真正source/参加者を使い、入力だけ凡打死へ替える。"""
    case = current_case(copy.deepcopy(SOURCE))
    case["request"]["t1"]["resultId"] = "batting-result.batted-out"
    case["request"]["t1"]["thirdOutObservation"] = "batter-before-first"
    return case


def _observations(case):
    """OUT3-01を打者公式参照付きで記録者が明示した原本。"""
    return {
        "pitchTypeKey": "fixture.fastball",
        "course": {"unit": "1/263", "x": "132", "y": "131"},
        "pitchSpeed": {"kmh": None, "outsideRangeConfirmed": False},
        "stance": None,
        "battingSide": None,
        "resultId": "batting-result.batted-out",
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
        "thirdOutObservation": {
            "kind": "batter-before-first",
            "batter": {
                "kind": "official",
                "player_id": case["request"]["source"]["participants"]["batterId"],
            },
        },
        "thirdOutTimingByRunner": {},
    }


def _values(case):
    """実hostの出力を封印し、数学値は変更しない。"""
    request = LineupPrefixRequest.model_validate_json(json.dumps(case["request"]))
    response = evaluate_lineup_prefix_continuation(request)
    assert isinstance(response, LineupPrefixSuccess)
    request, response = seal_lineup_wire(request, response)
    observed = BattedHitPlayObservations.model_validate_json(
        json.dumps(_observations(case))
    )
    calc = LineupPitchCalculation.model_validate_json(
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
    return request, response, observed, calc


def test_actual_batted_out_third_out_is_sealed_into_v3_payload():
    """唯一host出力を先置き正本flagと照合し、V7/V8の全値を往復する。"""
    case = _case()
    request, response, observed, calc = _values(case)
    assert response.ok is True
    flags = next(
        row["statFlags"]
        for row in MATRIX["matrixRows"]
        if row["resultId"] == "batting-result.batted-out"
    )
    assert response.value.t1.stat_flags.model_dump(by_alias=True) == flags
    assert response.value.t1.out_effect.count == "1"
    assert response.value.t1.batter_destination.kind == "out"
    assert request.t1.before.state_fields.score.away == "5"
    assert request.t1.before.state_fields.score.home == "3"
    assert response.value.t1.after.state_fields.half == "bottom"
    assert (
        request.t1.before.scoreboard.inning_scores
        == response.value.t1.after.scoreboard.inning_scores
    )
    require_batted_hit_observations(request.t1, observed)
    v7, v8 = format_batted_hit_prefix_payload(observed, calc)
    decoded = read_lineup_pitch_payload(
        v7, v8, expected_calculation=calc, require_current_rbi=True
    )
    assert decoded.observations == observed


@pytest.mark.parametrize("change", ["wrong-batter", "missing-third", "wrong-result"])
def test_batted_out_unknown_or_mismatched_observation_is_rejected(change):
    """別打者・第3アウト欠落・結果差替えを原本成功へ変換しない。"""
    case = _case()
    _, _, observed, calc = _values(case)
    v7, v8 = format_batted_hit_prefix_payload(observed, calc)
    data = json.loads(v7)
    if change == "wrong-batter":
        data["observations"]["thirdOutObservation"]["batter"]["player_id"] = (
            "33333333-3333-4333-8333-333333333333"
        )
    elif change == "missing-third":
        data["observations"]["thirdOutObservation"] = {"kind": "none"}
    else:
        data["observations"]["resultId"] = "batting-result.single"
    with pytest.raises(TerminalPitchPayloadError):
        read_lineup_pitch_payload(json.dumps(data), v8, expected_calculation=calc)
