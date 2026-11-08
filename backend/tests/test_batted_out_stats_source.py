"""凡打の原観測と唯一T1から、盗塁なしの明示集合だけを供給する。"""

import copy
import json
from uuid import uuid4

import pytest
from test_batted_out_prefix_payload import _case, _values

from pitchlog.stats.facts import evaluate_native_projection, native_projection
from pitchlog.sync.terminal_pitch_payload import format_batted_hit_prefix_payload


@pytest.fixture(scope="module")
def batted_out_payload():
    """実artifactの出力をそのまま用い、T5計算を試験側で複製しない。"""
    _, _, observed, calculation = _values(_case())
    raw, _ = format_batted_hit_prefix_payload(observed, calculation)
    return json.loads(raw)


@pytest.mark.parametrize(
    "failure",
    [None, "wrong-result", "wrong-third", "wrong-batter", "runner", "wrong-out"],
)
def test_batted_out_steal_source_requires_original_observations(
    batted_out_payload, failure
):
    """欠落・改変を0へ補わず、元の確定した無走塁だけ0にする。"""
    payload = copy.deepcopy(batted_out_payload)
    observed = payload["observations"]
    if failure == "wrong-result":
        observed["resultId"] = "batting-result.single"
    elif failure == "wrong-third":
        observed["thirdOutObservation"] = {"kind": "none"}
    elif failure == "wrong-batter":
        observed["thirdOutObservation"]["batter"]["player_id"] = str(uuid4())
    elif failure == "runner":
        payload["calculation"]["request"]["source"]["runners"] = [{"base": "1"}]
    elif failure == "wrong-out":
        payload["calculation"]["response"]["value"]["t1"]["outEffect"] = {
            "count": "0",
            "targets": [],
        }
    projection = native_projection(payload, source_event_id=uuid4())
    result = evaluate_native_projection(payload, source_event_id=uuid4())
    steals = result["metrics"]["stolen_bases"]
    assert (projection["completeness"]["steals"] == "complete") == (failure is None)
    assert ("steal_attempts" in projection) == (failure is None)
    if failure is None:
        assert (steals["state"], steals["value"]) == ("available", "0")
    else:
        assert steals["state"] == "source_unavailable"
