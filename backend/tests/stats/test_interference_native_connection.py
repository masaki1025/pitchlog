"""実妨害host原本から既唯一T5核への閉射影を確認する。"""

import copy
import json
from pathlib import Path
from uuid import UUID

import pytest
from test_interference_play_row import (
    ARTIFACT,
    PITCH,
    _actual,
    _actual_adopted_error,
    _actual_old_batted_runtime,
)

from pitchlog.domainrt.host import open_domain_host
from pitchlog.stats.facts import evaluate_native_projection, native_projection

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "case,nonzero",
    (
        ("penalty", {"catcher_interference_reached": "1", "pa": "1"}),
        ("play", {"h": "1", "total_bases": "1", "pa": "1"}),
        ("obstruction", {"runner_interference_reached": "1", "pa": "1"}),
        ("offensive", {"pitching_outs": "1", "ab": "1"}),
    ),
)
def test_actual_host_interference_uses_existing_t5(case, nonzero):
    """4原V7のフラグと確定空走者を生成T5へ転記する。"""
    _, payload = copy.deepcopy(_actual(case))
    event_id = UUID(payload["calculation"]["request"]["playIdentity"]["eventId"])
    projection = native_projection(payload, source_event_id=event_id)
    assert projection["runner_scores"] == []
    assert projection["steal_attempts"] == []
    assert projection["completeness"]["runs_rbi"] == "complete"
    assert projection["completeness"]["steals"] == "complete"
    result = evaluate_native_projection(payload, source_event_id=event_id)
    for name, value in nonzero.items():
        assert result["metrics"][name]["value"] == value
    assert result["metrics"]["runs"]["value"] == "0"
    assert result["metrics"]["rbi"]["value"] == "0"


@pytest.mark.parametrize(
    "mutation",
    (
        "missing-effects",
        "extra-effects",
        "changed-result",
        "changed-ruling",
        "changed-participant",
        "changed-flags",
        "changed-observation",
    ),
)
def test_interference_t5_rejects_inconsistent_original_or_effect(mutation):
    """同じ原本から外れた効果・裁定・参加者を旧算入へ落とさない。"""
    _, payload = copy.deepcopy(_actual("penalty"))
    value = payload["calculation"]["response"]["value"]
    if mutation == "missing-effects":
        del value["runnerScoreEffects"]
    elif mutation == "extra-effects":
        value["runnerScoreEffects"] = [
            {"base": "1", "validRun": True, "rbiCredited": True}
        ]
    elif mutation == "changed-result":
        payload["observations"]["resultId"] = "secondary-result.obstruction"
    elif mutation == "changed-ruling":
        payload["observations"]["interferenceRuling"]["adopted"]["kind"] = "play-result"
    elif mutation == "changed-participant":
        payload["participants"]["batterId"] = str(UUID(int=88))
    elif mutation == "changed-flags":
        value["t1"]["statFlags"]["打点"] = True
    else:
        payload["observations"]["unknown"] = True
    event_id = UUID(payload["calculation"]["request"]["playIdentity"]["eventId"])
    with pytest.raises(ValueError):
        native_projection(payload, source_event_id=event_id)


@pytest.mark.parametrize("operation", ("error", "sacrifice-bunt-error"))
def test_adopted_error_keeps_plain_batted_all_27_facts_and_fielder_credit(
    operation,
):
    """元走者あり実859採用結果は旧通常結果の全27値を維持する。"""
    _, payload = copy.deepcopy(_actual_adopted_error(operation))
    event_id = UUID(payload["calculation"]["request"]["playIdentity"]["eventId"])
    fielder = payload["observations"]["officialScoringPayload"]["errors"][0]["fielder"][
        "player_id"
    ]
    projection = native_projection(payload, source_event_id=event_id)
    assert projection["participants"]["error_fielder_id"] == fielder
    assert projection["completeness"]["steals"] == "complete"
    assert projection["steal_attempts"] == []
    result = evaluate_native_projection(payload, source_event_id=event_id)
    assert result["metrics"]["fielding_errors"] == {
        "state": "available",
        "value": "1",
        "display": "1",
        "reason": None,
        "credits": [{"player_id": fielder, "quantity": "1"}],
    }
    plain_index = 6 if operation == "error" else 9
    _, plain_payload = _actual_old_batted_runtime(plain_index)
    plain_event = UUID(
        plain_payload["calculation"]["request"]["playIdentity"]["eventId"]
    )
    plain_result = evaluate_native_projection(
        plain_payload, source_event_id=plain_event
    )
    assert result["metrics"] == plain_result["metrics"]
    altered = copy.deepcopy(payload)
    altered["observations"]["officialScoringPayload"]["errors"][0]["count"] = 2
    with pytest.raises(ValueError):
        native_projection(altered, source_event_id=event_id)


@pytest.mark.parametrize("attempt", ("squeeze", "steal-home"))
def test_actual_loaded_penalty_keeps_run_credit_but_steal_attempt_unknown(attempt):
    """実859満塁裁定の得点IDを写し、授与を盗塁成功へ短絡しない。"""
    samples = json.loads(
        (
            ROOT
            / "backend/tests/fixtures/batted_operations_schema_runtime_requests_v1.json"
        ).read_text()
    )["samples"]
    request = copy.deepcopy(samples[7]["request"])
    request["source"]["executionArtifactSha256"] = ARTIFACT
    chosen = request["t1"]
    chosen.update(
        eventKind="secondary-result",
        resultId="secondary-result.batting-interference",
        officialScoringPayload="no-error",
        runnerAdvanceOverrides="not-applied",
        thirdOutObservation="none",
        interferenceRuling={
            "kind": "batting-interference",
            "adopted": {"kind": "penalty-award"},
            "third_base_scoring_attempt": {"kind": "observed", "value": attempt},
        },
    )
    chosen.pop("outRunner", None)
    chosen.pop("rbiRulingByRunner", None)
    with open_domain_host() as host:
        response = json.loads(
            host.call("deriveLineupPlayPrefixWithContinuation", json.dumps(request))
        )
    assert response["ok"] is True
    payload = {
        "formatVersion": "play-prefix-play-v3",
        "participants": response["value"]["beforeParticipants"],
        "observations": {
            **PITCH,
            "resultId": chosen["resultId"],
            "interferenceRuling": chosen["interferenceRuling"],
        },
        "calculation": {
            "formatVersion": "play-prefix-calculation-v3",
            "artifactSha256": ARTIFACT,
            "request": request,
            "response": response,
        },
    }
    event_id = UUID(request["playIdentity"]["eventId"])
    projection = native_projection(payload, source_event_id=event_id)
    third = next(r for r in request["source"]["runners"] if r["base"] == "3")
    assert projection["runner_scores"] == [
        {
            "runner_id": third["runnerId"],
            "responsible_pitcher_id": third["responsiblePitcherId"],
            "valid_run": True,
            "rbi_credited": True,
            "rbi_batter_id": request["source"]["participants"]["batterId"],
        }
    ]
    assert projection["completeness"]["steals"] == "unavailable"
    assert "steal_attempts" not in projection
    metrics = evaluate_native_projection(payload, source_event_id=event_id)["metrics"]
    assert metrics["runs"]["value"] == "1"
    assert metrics["rbi"]["value"] == "1"
    assert metrics["stolen_bases"]["state"] == "source_unavailable"
