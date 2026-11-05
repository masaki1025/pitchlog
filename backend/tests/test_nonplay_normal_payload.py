"""新profileの手導出期待と実host/原wireの全比較。DB証拠ではない。"""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from pitchlog.domainrt.lineup_play_prefix_continuation import (
    decode_nonplay_lineup_prefix_request,
    evaluate_nonplay_lineup_prefix_continuation,
)
from pitchlog.sync.terminal_pitch_payload import (
    NonplayPitchCalculation,
    TerminalPitchPayloadError,
    read_lineup_pitch_payload,
)


def fixture_values(index=4):
    """既承認数学手例/名簿派生を再利用し、製品出力から期待を採取しない。"""
    p = Path(__file__).parent / "domainrt/test_lineup_play_prefix_continuation.py"
    spec = importlib.util.spec_from_file_location("nonplay_math_reference", p)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    q = module._nonplay_request(index)
    expected = module._nonplay_expected(q)
    calc = {
        "formatVersion": "nonplay-prefix-calculation-v1",
        "artifactSha256": q["source"]["checkpoint"]["content"][
            "executionArtifactSha256"
        ],
        "request": q,
        "response": expected,
    }
    v7 = {
        "formatVersion": "play-prefix-play-v3",
        "observations": {
            "pitchTypeKey": "pitch-type.straight",
            "course": {"unit": "1/263", "x": "131", "y": "132"},
            "pitchSpeed": {"kmh": None, "outsideRangeConfirmed": False},
            "stance": None,
            "battingSide": None,
        },
        "participants": expected["value"]["beforeParticipants"],
        "calculation": calc,
    }
    return v7, expected["value"]["newHistoryEntry"]["difference"]


def test_real_host_and_closed_payload_all_values():
    """実artifact一回の応答を既独立手例の全fieldへ照合する。"""
    v7, v8 = fixture_values()
    expected = v7["calculation"]["response"]
    actual = evaluate_nonplay_lineup_prefix_continuation(
        decode_nonplay_lineup_prefix_request(json.dumps(v7["calculation"]["request"]))
    )
    assert actual.model_dump(mode="json", by_alias=True, exclude_unset=True) == expected
    calc = NonplayPitchCalculation.model_validate_json(json.dumps(v7["calculation"]))
    got = read_lineup_pitch_payload(
        json.dumps(v7), json.dumps(v8), expected_calculation=calc
    )
    assert got.model_dump(mode="json", by_alias=True, exclude_unset=True) == v7


@pytest.mark.parametrize(
    "field",
    [
        "artifact",
        "response",
        "participant",
        "v8",
        "extra",
        "unknown-profile",
        "hit",
        "position",
        "proposal",
    ],
)
def test_payload_mutations_rejected(field):
    """実計算へ期待を追随せず別面/余剰/未知profileを拒否する。"""
    v7, v8 = fixture_values()
    calc = NonplayPitchCalculation.model_validate_json(json.dumps(v7["calculation"]))
    bad = copy.deepcopy(v7)
    if field == "artifact":
        bad["calculation"]["artifactSha256"] = "0" * 64
    elif field == "response":
        bad["calculation"]["response"]["value"]["t1"]["after"]["stateFields"][
            "state.count.balls"
        ] = "2"
    elif field == "participant":
        bad["participants"]["pitcherId"] = "00000000-0000-4000-8000-000000000999"
    elif field == "v8":
        v8["stateFields"] = {}
    elif field == "extra":
        bad["calculation"]["extra"] = True
    elif field == "unknown-profile":
        bad["calculation"]["formatVersion"] = "unknown"
    elif field == "hit":
        bad["calculation"]["request"]["t1"]["resultId"] = "batting-result.single"
    elif field == "position":
        bad["calculation"]["request"]["sourcePosition"]["d1"] = "1"
    else:
        bad["calculation"]["request"]["nextCheckpoint"]["digest"] = "0" * 64
    with pytest.raises(TerminalPitchPayloadError):
        read_lineup_pitch_payload(
            json.dumps(bad), json.dumps(v8), expected_calculation=calc
        )
