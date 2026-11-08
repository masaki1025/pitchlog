"""実妨害host原本から既唯一T5核への閉射影を確認する。"""

import copy
from uuid import UUID

import pytest
from test_interference_play_row import _actual

from pitchlog.stats.facts import evaluate_native_projection, native_projection


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
