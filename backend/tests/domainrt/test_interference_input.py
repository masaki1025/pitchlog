"""妨害v3入力の裁定種別と実source選手参照を閉検査する。"""

import copy
import json
from pathlib import Path

import pytest

from pitchlog.domainrt.lineup_play_prefix_continuation import (
    AdjudicatedInterferenceT1Input,
    BattingInterferencePenaltyT1Input,
    LineupPrefixProtocolError,
    decode_lineup_prefix_request,
)

ROOT = Path(__file__).resolve().parents[3]
BASE = json.loads(
    (ROOT / "contracts/state-transition/batted_hit_prefix_cases_v1.json").read_text()
)["cases"][0]["request"]


def _batter_ref(actual: str) -> dict[str, object]:
    return {"kind": "batter", "batter_id": {"kind": "official", "player_id": actual}}


def test_penalty_is_distinct_from_legacy_batted_input():
    """旧打球のnot-required形を広げずsecondary専用実型を選ぶ。"""
    wire = copy.deepcopy(BASE)
    wire["t1"].update(
        eventKind="secondary-result",
        resultId="secondary-result.batting-interference",
        interferenceRuling={
            "kind": "batting-interference",
            "adopted": {"kind": "penalty-award"},
            "third_base_scoring_attempt": {"kind": "not-required"},
        },
    )
    parsed = decode_lineup_prefix_request(json.dumps(wire))
    assert type(parsed.t1) is BattingInterferencePenaltyT1Input
    wire["t1"]["interferenceRuling"]["adopted"] = {
        "kind": "play-result",
        "resultId": "batting-result.single",
    }
    with pytest.raises(LineupPrefixProtocolError):
        decode_lineup_prefix_request(json.dumps(wire))


def test_obstruction_person_is_bound_to_actual_batter():
    """未提示/別人/temporaryの審判参照を実sourceへ補完しない。"""
    wire = copy.deepcopy(BASE)
    actual = wire["source"]["participants"]["batterId"]
    ref = _batter_ref(actual)
    wire["t1"] = {
        "eventKind": "secondary-result",
        "resultId": "secondary-result.obstruction",
        "pitchEventKind": "pitch-event",
        "before": wire["t1"]["before"],
        "interferenceRuling": {
            "kind": "obstruction",
            "play_kind": "play-on-obstructed-runner",
            "obstructed": ref,
            "awarded_destinations": [{"person": ref, "destination": "first"}],
            "out_targets": [],
            "batter_before_first": True,
        },
    }
    parsed = decode_lineup_prefix_request(json.dumps(wire))
    assert type(parsed.t1) is AdjudicatedInterferenceT1Input
    for wrong in [
        _batter_ref("55555555-5555-4555-8555-555555555555"),
        {"kind": "batter", "batter_id": {"kind": "temporary", "temporary_id": actual}},
    ]:
        bad = copy.deepcopy(wire)
        bad["t1"]["interferenceRuling"]["obstructed"] = wrong
        with pytest.raises(LineupPrefixProtocolError):
            decode_lineup_prefix_request(json.dumps(bad))


def test_offensive_kind_and_out_target_are_closed():
    """守備妨害は非空アウト対象を要求し、走塁妨害へ読み替えない。"""
    wire = copy.deepcopy(BASE)
    actual = wire["source"]["participants"]["batterId"]
    ref = _batter_ref(actual)
    wire["t1"] = {
        "eventKind": "secondary-result",
        "resultId": "secondary-result.offensive-interference",
        "pitchEventKind": "pitch-event",
        "before": wire["t1"]["before"],
        "interferenceRuling": {
            "kind": "offensive-interference",
            "out_targets": [ref],
            "return_bases": [],
        },
    }
    parsed = decode_lineup_prefix_request(json.dumps(wire))
    assert type(parsed.t1) is AdjudicatedInterferenceT1Input
    wire["t1"]["interferenceRuling"]["out_targets"] = []
    with pytest.raises(LineupPrefixProtocolError):
        decode_lineup_prefix_request(json.dumps(wire))
