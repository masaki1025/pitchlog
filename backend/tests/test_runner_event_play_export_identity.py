"""同TX CSV原本のNP非該当を原観測/物理行で閉照合する。実保存証拠とは別。"""

import copy
import json
from uuid import UUID

import pytest
from test_runner_event_wire import _CASES, _payload

from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
from pitchlog.sync.play_export_identity import (
    PlayExportIdentityUnavailable,
    _course_screen,
)
from pitchlog.sync.terminal_pitch_payload import read_lineup_pitch_payload


def _source(index):
    payload, calc = _payload(_CASES[index])
    checked = read_lineup_pitch_payload(
        json.dumps(payload),
        json.dumps(
            payload["calculation"]["response"]["value"]["newHistoryEntry"]["difference"]
        ),
        expected_calculation=calc,
    )
    q = calc.request
    row = pitch_physical_row(
        checked.observations,
        checked.participants,
        q.t1.result_id,
        tenant_id=UUID(q.prefix_ref.tenant_id),
        game_id=UUID(q.prefix_ref.game_id),
        source_event_id=UUID(q.play_identity.event_id),
        row_id=UUID(q.play_identity.play_id),
        play_number=1,
    )
    return payload, row


@pytest.mark.parametrize("index", [0, 1, 5])
def test_actual_np_original_has_no_course_without_faking_pitch(index):
    """牽制/ボークの原観測と実mapper行だけから非該当を写す。"""
    payload, row = _source(index)
    assert _course_screen(payload, row) == (None, None)
    assert "course" not in payload["observations"]
    assert all(
        row[key] is None
        for key in (
            "course_x",
            "course_y",
            "pitch_type_key",
            "pitch_speed",
            "stance",
            "batting_side",
        )
    )


@pytest.mark.parametrize(
    "target",
    [
        "course",
        "missing-course",
        "pitch-kind",
        "primary-result",
        "body-extra",
        "different-observation",
        "wrong-result",
        "unknown-result",
    ],
)
def test_unknown_or_repaired_np_does_not_become_empty_course(target):
    """原値/投球区分/参照元の不一致をNULLへ補修しない。"""
    payload, row = _source(0)
    if target == "course":
        row["course_x"] = 0.5
    elif target == "missing-course":
        del row["course_x"]
    elif target == "pitch-kind":
        row["event_kind"] = "pitch"
    elif target == "primary-result":
        payload["observations"]["runnerObservation"]["primaryResultId"] = (
            "batting-result.ball"
        )
    elif target == "body-extra":
        payload["observations"]["course"] = {"unit": "1/263", "x": "0", "y": "0"}
    elif target == "different-observation":
        payload["observations"]["runnerObservation"]["perPitch"]["runnerEventPayload"][
            "by_runner"
        ]["first"]["attempted_base"] = "second"
    elif target == "wrong-result":
        row["batting_result_key"] = "batting-result.ball"
    else:
        payload["calculation"]["request"]["t1"]["resultId"] = "unknown"
        for o in [
            payload["observations"]["runnerObservation"],
            payload["calculation"]["request"]["t1"]["runnerObservation"],
        ]:
            o["perPitch"]["resultId"] = "unknown"
    before = copy.deepcopy(payload)
    with pytest.raises(PlayExportIdentityUnavailable):
        _course_screen(payload, row)
    assert payload == before


@pytest.mark.parametrize("index", [2, 3, 4, 6])
def test_real_pitch_still_uses_the_only_coordinate_generator(index):
    """実投球は旧正準kの唯一射影を維持し、NPへ落とさない。"""
    payload, row = _source(index)
    assert _course_screen(payload, row) == ("131", "131")


@pytest.mark.parametrize("index", [0, 1])
def test_na_plate_is_explicit_null_and_never_false_or_new_result(index, monkeypatch):
    """XC-05/07非該当を生成表示へ偽bool入力せず、元T1も変更しない。"""
    from dataclasses import replace

    from test_record_export_direct_projection import _identity

    from pitchlog.exports import record_projection as projection

    payload, row = _source(index)
    original = copy.deepcopy(payload)
    actual = projection._native_completion(payload, row)
    assert actual["打席の継続"] is None
    assert actual["イニング継続"] == ("イニング開始" if index == 1 else "イニング継続")
    assert actual["試合継続"] == "試合継続"
    identity = replace(_identity(), payload=payload, play=row)

    def forbidden(*args):
        pytest.fail("not-applicableを生成表示のbool引数へ偽装してはいけない")

    monkeypatch.setattr(projection, "plate_result_display", forbidden)
    assert projection._native_plate_display(identity) is None
    assert payload == original


@pytest.mark.parametrize(
    "target", ["missing-row", "wrong-row", "not-runner", "unknown-na"]
)
def test_arbitrary_na_is_not_silently_become_null(target):
    """閉NP以外のNA/未知をNULLやfalseへ補修しない。"""
    from pitchlog.exports.record_projection import (
        RecordedExportProjectionUnavailable,
        _native_completion,
    )

    payload, row = _source(0)
    if target == "missing-row":
        row = None
    elif target == "wrong-row":
        row["course_x"] = 0.5
    elif target == "not-runner":
        payload["calculation"]["request"]["t1"]["eventKind"] = "secondary-result"
    else:
        payload["calculation"]["response"]["value"]["t1"]["plateAppearanceEnded"] = (
            "unknown"
        )
    with pytest.raises(RecordedExportProjectionUnavailable):
        _native_completion(payload, row)
