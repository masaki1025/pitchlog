"""CSV記録原本の選手集合を真正V3保存値で固定する。"""

import json
from pathlib import Path
from uuid import UUID

import pytest

from pitchlog.sync.play_export_identity import (
    PlayExportIdentityUnavailable,
    _course_screen,
    _player_ids,
)

_ROOT = Path(__file__).resolve().parents[2]
_CASES = json.loads(
    (
        _ROOT / "contracts/state-transition/lineup_play_prefix_payload_vectors_v1.json"
    ).read_text()
)["cases"]


def _source_with_runner():
    """静的v3ケースから走者を持つ原本を選ぶ。"""
    return next(
        case["V7"]
        for case in _CASES
        if case["V7"]["calculation"]["request"]["source"].get("runners")
    )


def _initial_lineups(payload):
    """保存開始名簿の入力形だけを静的sourceと同じIDで作る。"""
    source = payload["calculation"]["request"]["source"]["lineup"]
    return tuple(
        {
            "entries_with_uniform_number_snapshot": [
                {"player_id": identifier}
                for identifier in source[side]["battingOrder"].values()
            ]
        }
        for side in ("away", "home")
    )


def test_v3_identity_includes_current_pitcher_and_responsible_runner() -> None:
    """開始時18人だけに限定せず交代投手・走者の実原本を保持する。"""
    payload = _source_with_runner()
    source = payload["calculation"]["request"]["source"]
    players = _player_ids(payload, _initial_lineups(payload), {})
    for identifier in (
        payload["participants"]["pitcherId"],
        source["lineup"]["home"]["pitcherId"],
        source["runners"][0]["runnerId"],
        source["runners"][0]["responsiblePitcherId"],
    ):
        assert UUID(identifier) in players


def test_unknown_runner_source_does_not_use_current_roster_as_fallback() -> None:
    """走者ID欠落を現名簿・0で補わず拒否する。"""
    payload = _source_with_runner()
    payload = json.loads(json.dumps(payload))
    payload["calculation"]["request"]["source"]["runners"][0].pop("runnerId")
    with pytest.raises(PlayExportIdentityUnavailable):
        _player_ids(payload, _initial_lineups(payload), {})


def test_recorded_v3_course_uses_only_generated_b7_target() -> None:
    """真正V3保存観測をDouble逆算せず表示targetへ渡す。"""
    payload = _CASES[0]["V7"]
    assert payload["observations"]["course"] == {
        "unit": "1/263",
        "x": "131",
        "y": "132",
    }
    assert _course_screen(payload) == ("131", "131")


@pytest.mark.parametrize("invalid", ["decimal", "extra", "missing"])
def test_recorded_course_rejects_unknown_shape(invalid: str) -> None:
    """正準外の記録観測をCSV用に丸め直さない。"""
    payload = json.loads(json.dumps(_CASES[0]["V7"]))
    course = payload["observations"]["course"]
    if invalid == "decimal":
        course["x"] = 0.5
    elif invalid == "extra":
        course["other"] = "0"
    else:
        del course["unit"]
    with pytest.raises(PlayExportIdentityUnavailable):
        _course_screen(payload)


def test_intentional_walk_course_requires_closed_non_pitch_source_and_saved_null():
    """申告敬遠の座標未観測だけを保存PlayRowのNULL二欄へ束縛する。"""
    payload = json.loads(json.dumps(_CASES[0]["V7"]))
    payload["observations"] = {"kind": "intentional-walk"}
    payload["calculation"]["request"]["t1"]["pitchEventKind"] = "non-pitch-event"
    payload["calculation"]["request"]["t1"]["resultId"] = (
        "batting-result.intentional-walk"
    )
    play = {
        "event_kind": "non_pitch",
        "batting_result_key": "batting-result.intentional-walk",
        "course_x": None,
        "course_y": None,
    }
    assert _course_screen(payload, play) == (None, None)
    for field, bad in (
        ("course_x", 0.0),
        ("course_y", 0.0),
        ("event_kind", "pitch"),
    ):
        broken = play | {field: bad}
        with pytest.raises(PlayExportIdentityUnavailable):
            _course_screen(payload, broken)
    payload["observations"] = {"kind": "intentional-walk", "course": None}
    with pytest.raises(PlayExportIdentityUnavailable):
        _course_screen(payload, play)
    payload["observations"] = {"kind": "intentional-walk"}
    payload["calculation"]["request"]["t1"]["pitchEventKind"] = "pitch-event"
    with pytest.raises(PlayExportIdentityUnavailable):
        _course_screen(payload, play)
    payload["calculation"]["request"]["t1"]["pitchEventKind"] = "non-pitch-event"
    play["batting_result_key"] = "batting-result.walk"
    with pytest.raises(PlayExportIdentityUnavailable):
        _course_screen(payload, play)


def test_pitch_course_missing_is_not_converted_to_non_pitch_null():
    """投球の正準座標欠測を非投球の未観測へ混同しない。"""
    payload = json.loads(json.dumps(_CASES[0]["V7"]))
    del payload["observations"]["course"]
    play = {"event_kind": "pitch", "course_x": None, "course_y": None}
    with pytest.raises(PlayExportIdentityUnavailable):
        _course_screen(payload, play)
