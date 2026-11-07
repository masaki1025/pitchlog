"""唯一候補artifactと閉V7/V8の申告敬遠接合。"""

import copy
import json
import os
from pathlib import Path

import pytest

from pitchlog.domainrt.host import NodeDomainHost
from pitchlog.domainrt.lineup_play_prefix_continuation import (
    LineupPrefixRequest,
    decode_lineup_prefix_response,
    seal_lineup_wire,
)
from pitchlog.sync.nonpitch_payload import format_intentional_walk_prefix_payload
from pitchlog.sync.terminal_pitch_payload import (
    LineupPitchCalculation,
    TerminalPitchPayloadError,
    read_lineup_pitch_payload,
)

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = Path(
    os.environ.get("PITCHLOG_NONPITCH_ARTIFACT_DIR", ROOT / "frontend/public/domain")
)


def _calculation():
    """旧v3例の正規shapeから厳密一三塁座標へ移し、実hostを一回使う。"""
    vectors = json.loads(
        (
            ROOT / "contracts/state-transition/lineup_play_prefix_cases_v1.json"
        ).read_text()
    )
    original = next(
        c for c in vectors["cases"] if c["caseId"] == "V3-STRIKEOUT-1-B1-O2"
    )
    request = copy.deepcopy(original["request"])
    request["t1"]["resultId"] = "batting-result.intentional-walk"
    request["t1"]["pitchEventKind"] = "non-pitch-event"
    for state in (
        request["t1"]["before"]["stateFields"],
        request["source"]["after"]["stateFields"],
    ):
        state["state.count.strikes"] = "0"
        state["state.count.balls"] = "0"
        state["state.outs"] = "0"
    request["source"]["t2"]["facts"]["afterOuts"] = "0"
    with NodeDomainHost(
        ARTIFACT / "pitchlog-domain.js", ARTIFACT / "pitchlog-domain.json"
    ) as host:
        request["source"]["executionArtifactSha256"] = host.artifact_sha256
        response = decode_lineup_prefix_response(
            host.call("deriveLineupPlayPrefixWithContinuation", json.dumps(request))
        )
        assert response.ok
        parsed = LineupPrefixRequest.model_validate_json(json.dumps(request))
        sealed_request, sealed_response = seal_lineup_wire(parsed, response)
        return LineupPitchCalculation.model_validate_json(
            json.dumps(
                {
                    "formatVersion": "play-prefix-calculation-v3",
                    "artifactSha256": host.artifact_sha256,
                    "request": sealed_request.model_dump(
                        mode="json", by_alias=True, exclude_unset=True
                    ),
                    "response": sealed_response.model_dump(
                        mode="json", by_alias=True, exclude_unset=True
                    ),
                }
            )
        )


def test_intentional_walk_has_no_pitch_observations_and_full_difference():
    """真正候補artifact応答の全値をV7/V8へ閉じて保持する。"""
    calc = _calculation()
    v7, v8 = format_intentional_walk_prefix_payload(calc)
    assert json.loads(v7)["observations"] == {"kind": "intentional-walk"}
    assert json.loads(
        v8
    ) == calc.response.value.new_history_entry.difference.model_dump(
        mode="json", by_alias=True, exclude_unset=True
    )
    payload = read_lineup_pitch_payload(v7, v8, expected_calculation=calc)
    assert payload.calculation == calc
    assert payload.participants.model_dump(mode="json", by_alias=True) == (
        calc.response.value.before_participants.model_dump(mode="json", by_alias=True)
    )


@pytest.mark.parametrize(
    "mutation",
    ["pitch-field", "unknown", "result", "pitch-kind", "participant", "difference"],
)
def test_nonpitch_v7_v8_rejects_omission_or_wrong_full_member(mutation):
    """未知観測・偽投球・別結果・参加者・差分の混在を拒否する。"""
    calc = _calculation()
    v7, v8 = format_intentional_walk_prefix_payload(calc)
    data = json.loads(v7)
    diff = json.loads(v8)
    if mutation == "pitch-field":
        data["observations"]["pitchTypeKey"] = "fixture.fastball"
    elif mutation == "unknown":
        data["observations"]["kind"] = "unknown"
    elif mutation == "result":
        data["calculation"]["request"]["t1"]["resultId"] = "batting-result.walk"
    elif mutation == "pitch-kind":
        data["calculation"]["request"]["t1"]["pitchEventKind"] = "pitch-event"
    elif mutation == "participant":
        data["participants"]["batterId"] = data["participants"]["pitcherId"]
    elif mutation == "difference":
        diff["kind"] = "unknown"
    with pytest.raises(TerminalPitchPayloadError):
        read_lineup_pitch_payload(
            json.dumps(data), json.dumps(diff), expected_calculation=calc
        )
