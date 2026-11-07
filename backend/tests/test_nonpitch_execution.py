"""申告敬遠の非投球物理行と閉入力の対向。"""

import json
from uuid import UUID

import pytest

from pitchlog.sync.nonpitch_execution import intentional_walk_physical_row
from pitchlog.sync.nonpitch_payload import IntentionalWalkObservations
from pitchlog.sync.ordinary_pitch_payload import OrdinaryPitchParticipants

IDS = [UUID(int=i) for i in range(1, 8)]


def _people() -> OrdinaryPitchParticipants:
    """保存資格ではない試験参加者を作る。"""
    return OrdinaryPitchParticipants(
        batterId=str(IDS[3]),
        pitcherId=str(IDS[4]),
        catcherId=str(IDS[5]),
        battingOrder="2",
    )


def _row(observation=None, *, result="batting-result.intentional-walk"):
    """保存には接続せず物理41列だけを評価する。"""
    return intentional_walk_physical_row(
        IntentionalWalkObservations(kind="intentional-walk")
        if observation is None
        else observation,
        _people(),
        result,
        tenant_id=IDS[0],
        game_id=IDS[1],
        source_event_id=IDS[2],
        row_id=IDS[6],
        play_number=7,
    )


def test_intentional_walk_is_full_nonpitch_row_without_pseudo_pitch():
    """旧41列を保持し、コース・球種・球速をNULLで保存する。"""
    row = _row()
    assert len(row) == 41
    assert row["event_kind"] == "non_pitch"
    assert row["batting_result_key"] == "batting-result.intentional-walk"
    assert row["source_event_id"] == str(IDS[2])
    assert row["batter_id"] == str(IDS[3])
    assert row["pitcher_id"] == str(IDS[4])
    assert row["catcher_id"] == str(IDS[5])
    assert row["play_number"] == 7
    for field in ("course_x", "course_y", "pitch_type_key", "pitch_speed"):
        assert row[field] is None


@pytest.mark.parametrize(
    "observation,result",
    [
        ({"kind": "intentional-walk"}, "batting-result.intentional-walk"),
        (IntentionalWalkObservations(kind="intentional-walk"), "batting-result.walk"),
    ],
)
def test_wrong_type_or_result_cannot_become_nonpitch_row(observation, result):
    """字面の一致や通常四球では非投球行を発行できない。"""
    with pytest.raises(ValueError):
        _row(observation, result=result)


@pytest.mark.parametrize(
    "wire",
    [
        {"kind": "intentional-walk", "pitchTypeKey": "fixture.fastball"},
        {"kind": "intentional-walk", "course": None},
        {"kind": "intentional-walk", "resultId": "batting-result.walk"},
        {"kind": "unknown"},
    ],
)
def test_closed_observation_rejects_pitch_fields_and_unknown(wire):
    """球種等の偽入力と未知非投球を閉型で拒否する。"""
    with pytest.raises(ValueError):
        IntentionalWalkObservations.model_validate_json(json.dumps(wire))
