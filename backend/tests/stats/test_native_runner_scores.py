"""到達ID/責任/打点の写像を検査する。野球計算の別oracleは作らない。"""

import copy
import json
from pathlib import Path
from uuid import UUID

import pytest

from pitchlog.stats.facts import evaluate_native_projection, native_projection

ROOT = Path(__file__).resolve().parents[3]
CASES = json.loads(
    (ROOT / "contracts/state-transition/batted_hit_prefix_cases_v1.json").read_text()
)["cases"]
EVENT = UUID("00000000-0000-0000-0000-000000000701")


def _payload(case):
    """正準契約のrequest/expectedを無変更で包み、明示no-error観測を添える。"""
    return {
        "formatVersion": "play-prefix-play-v3",
        "participants": copy.deepcopy(case["expected"]["value"]["beforeParticipants"]),
        "observations": {
            "resultId": case["request"]["t1"]["resultId"],
            "officialScoringPayload": {
                "kind": "no-error",
                "errorCount": "0",
                "fielders": [],
            },
            "interferenceRuling": {"kind": "not-required"},
            "thirdOutObservation": {"kind": "none"},
            "thirdOutTimingByRunner": {},
            "runnerAdvanceOverridesByRunner": {"kind": "not-applied", "overrides": []},
        },
        "calculation": {
            "formatVersion": "play-prefix-calculation-v3",
            "request": copy.deepcopy(case["request"]),
            "response": copy.deepcopy(case["expected"]),
        },
    }


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["caseId"])
def test_canonical_hits_copy_exact_batter_credit_or_proven_empty(case):
    """正準19行の打者生還または非生還を写し、原値は変更しない。"""
    raw = _payload(case)
    before = copy.deepcopy(raw)
    result = evaluate_native_projection(raw, source_event_id=EVENT)
    scored = case["request"]["t1"]["resultId"] == "batting-result.home-run"
    people = raw["participants"]
    for metric, player in (
        ("runs", people["batterId"]),
        ("rbi", people["batterId"]),
        ("runs_allowed", people["pitcherId"]),
    ):
        assert result["metrics"][metric] == {
            "state": "available",
            "value": "1" if scored else "0",
            "display": "1" if scored else "0",
            "reason": None,
            "credits": [{"player_id": player, "quantity": "1"}] if scored else [],
        }
    assert raw == before


def _runner_payload(result, destinations, count):
    """adapterだけの手定入力。真正frame/実artifact成功との主張はしない。"""
    case = next(c for c in CASES if c["caseId"] == "BHP-BH-HomeRun-top-O1")
    raw = _payload(case)
    q = raw["calculation"]["request"]
    t1 = raw["calculation"]["response"]["value"]["t1"]
    q["t1"]["resultId"] = raw["observations"]["resultId"] = result
    q["t1"]["before"]["stateFields"]["state.score"] = {"home": "0", "away": "0"}
    t1["after"]["stateFields"]["state.score"] = {"home": "0", "away": count}
    lineup = q["source"]["lineup"]
    runners = [
        {
            "base": str(base),
            "runnerId": lineup["away"]["battingOrder"][str(base + 1)],
            "responsiblePitcherId": lineup["home"]["battingOrder"][str(base + 1)],
        }
        for base in destinations
    ]
    q["source"]["runners"] = runners
    overrides = {
        "kind": "applied",
        "overrides": [
            {"runnerBase": str(base), "destination": destination}
            for base, destination in destinations.items()
        ],
    }
    q["t1"]["runnerAdvanceOverrides"] = copy.deepcopy(overrides)
    raw["observations"]["runnerAdvanceOverridesByRunner"] = overrides
    for base, name in ((1, "first"), (2, "second"), (3, "third")):
        t1["runnerDefaultAdvance"][name] = {
            "modality": "forced" if base in destinations else "not-applicable",
            "destination": destinations.get(base),
        }
    t1["batterDestination"] = (
        {"kind": "score"}
        if result == "batting-result.home-run"
        else {"kind": "reach", "base": "2"}
    )
    return raw, runners


@pytest.mark.parametrize(
    "result,destinations,count,scoring_bases",
    [
        ("batting-result.single", {1: "3", 2: "4"}, "1", [2]),
        ("batting-result.double", {1: "3", 2: "4"}, "1", [2]),
        ("batting-result.triple", {1: "4", 2: "4"}, "2", [1, 2]),
        ("batting-result.home-run", {1: "4", 2: "4", 3: "4"}, "4", [1, 2, 3]),
    ],
)
def test_all_scoring_runner_ids_and_previous_responsible_pitchers_are_preserved(
    result, destinations, count, scoring_bases
):
    """非生還走者を加算せず、前任投手の責任を現在投手で補完しない。"""
    raw, runners = _runner_payload(result, destinations, count)
    projected = native_projection(raw, source_event_id=EVENT)
    chosen = [r for r in runners if int(r["base"]) in scoring_bases]
    expected = [
        {
            "runner_id": r["runnerId"],
            "responsible_pitcher_id": r["responsiblePitcherId"],
            "valid_run": True,
            "rbi_credited": True,
            "rbi_batter_id": raw["participants"]["batterId"],
        }
        for r in chosen
    ]
    if result == "batting-result.home-run":
        expected.append(
            {
                "runner_id": raw["participants"]["batterId"],
                "responsible_pitcher_id": raw["participants"]["pitcherId"],
                "valid_run": True,
                "rbi_credited": True,
                "rbi_batter_id": raw["participants"]["batterId"],
            }
        )
    assert projected["runner_scores"] == expected
    actual = evaluate_native_projection(raw, source_event_id=EVENT)["metrics"]
    for metric in ("runs", "rbi", "runs_allowed"):
        assert actual[metric]["state"] == "available"
        assert actual[metric]["value"] == count


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-scores",
        "missing-plan",
        "missing-pitcher",
        "third-out",
        "third-timing",
        "error",
        "interference",
        "score-mismatch",
        "rbi-false",
        "missing-observation",
        "unknown-result",
        "missing-overrides",
        "unconfirmed-overrides",
        "duplicate-runner",
    ],
)
def test_incomplete_or_unsupported_causality_stays_unavailable(mutation):
    """得点差や結果名で欠測の選手/打点を推測しない。"""
    raw, _ = _runner_payload("batting-result.triple", {1: "4", 2: "4"}, "2")
    q = raw["calculation"]["request"]
    t1 = raw["calculation"]["response"]["value"]["t1"]
    if mutation == "missing-scores":
        del t1["after"]["stateFields"]["state.score"]
    elif mutation == "missing-plan":
        del t1["runnerDefaultAdvance"]
    elif mutation == "missing-pitcher":
        del q["source"]["runners"][0]["responsiblePitcherId"]
    elif mutation == "third-out":
        t1["outEffect"]["count"] = "3"
    elif mutation == "third-timing":
        raw["observations"]["thirdOutTimingByRunner"] = {"1": "home-before-third-out"}
    elif mutation == "error":
        raw["observations"]["officialScoringPayload"]["kind"] = "error"
    elif mutation == "interference":
        q["t1"]["interferenceRuling"] = "required"
    elif mutation == "score-mismatch":
        t1["after"]["stateFields"]["state.score"]["away"] = "4"
    elif mutation == "rbi-false":
        t1["statFlags"]["打点"] = False
    elif mutation == "missing-observation":
        del raw["observations"]["thirdOutObservation"]
    elif mutation == "unknown-result":
        q["t1"]["resultId"] = "unknown"
    elif mutation == "missing-overrides":
        del raw["observations"]["runnerAdvanceOverridesByRunner"]
    elif mutation == "unconfirmed-overrides":
        raw["observations"]["runnerAdvanceOverridesByRunner"]["overrides"].pop()
    elif mutation == "duplicate-runner":
        q["source"]["runners"][1]["runnerId"] = q["source"]["runners"][0]["runnerId"]
    result = evaluate_native_projection(raw, source_event_id=EVENT)
    for key in ("runs", "rbi", "runs_allowed"):
        assert result["metrics"][key]["state"] == "source_unavailable"
        assert result["metrics"][key]["value"] is None
        assert result["metrics"][key]["credits"] == []


@pytest.mark.parametrize(
    "result_id", ["batting-result.ball", "batting-result.called-pitch"]
)
def test_canonical_ordinary_zero_is_complete_but_missing_destination_is_not(result_id):
    """正式初球原本の非生還・不変scoreを確認し、欠けた結果は0にしない。"""
    cases = json.loads(
        (ROOT / "backend/tests/fixtures/first_ball_payload_vectors_v1.json").read_text()
    )["cases"]
    raw = next(
        json.loads(c["v7Json"])
        for c in cases
        if json.loads(c["v7Json"])["calculation"]["request"]["t1"]["resultId"]
        == result_id
    )
    for metric in ("runs", "rbi", "runs_allowed"):
        assert evaluate_native_projection(raw, source_event_id=EVENT)["metrics"][
            metric
        ] == {
            "state": "available",
            "value": "0",
            "display": "0",
            "reason": None,
            "credits": [],
        }
    del raw["calculation"]["response"]["value"]["t1"]["batterDestination"]
    for metric in ("runs", "rbi", "runs_allowed"):
        assert (
            evaluate_native_projection(raw, source_event_id=EVENT)["metrics"][metric][
                "state"
            ]
            == "source_unavailable"
        )
