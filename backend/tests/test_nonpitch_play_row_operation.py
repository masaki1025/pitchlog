"""申告敬遠の閉物理行を既同TX PlayRow 登録へ接続する。"""

import json
from uuid import UUID

import pytest
from sqlalchemy import Insert

from pitchlog.db.game_state.models import PlayRow
from pitchlog.repositories.ordinary_pitch_operations import (
    PLAY_PREFIX_PLAY_OPERATIONS,
    OrdinaryPlayRowError,
)
from pitchlog.sync.nonpitch_execution import intentional_walk_physical_row
from pitchlog.sync.nonpitch_payload import IntentionalWalkObservations
from pitchlog.sync.ordinary_pitch_payload import OrdinaryPitchParticipants
from pitchlog.sync.ordinary_pitch_tokens import OrdinaryPlayRowInsertToken
from pitchlog.sync.terminal_pitch_tokens import PlayPrefixPlayRowInsertToken

IDS = tuple(UUID(int=i) for i in range(1, 9))


def _row() -> dict[str, object]:
    """単一物理mapperの出力を登録境界へ渡す。"""
    return intentional_walk_physical_row(
        IntentionalWalkObservations(kind="intentional-walk"),
        OrdinaryPitchParticipants(
            batterId=str(IDS[4]),
            pitcherId=str(IDS[5]),
            catcherId=str(IDS[6]),
            battingOrder="3",
        ),
        "batting-result.intentional-walk",
        tenant_id=IDS[0],
        game_id=IDS[1],
        source_event_id=IDS[2],
        row_id=IDS[3],
        play_number=3,
    )


def _token(
    row: dict[str, object],
    kind: type[OrdinaryPlayRowInsertToken | PlayPrefixPlayRowInsertToken] = (
        PlayPrefixPlayRowInsertToken
    ),
):
    """端末入力では発行できない保存tokenの形を試験だけで与える。"""
    return kind(
        IDS[1],
        2,
        3,
        6001,
        IDS[7],
        "wire-v1:" + "a" * 64,
        json.dumps(row),
    )


def test_exact_nonpitch_row_uses_existing_insert_and_preflight():
    """41列/同TX照合を保持し、球種やコースを補わない。"""
    row = _row()
    operation = PLAY_PREFIX_PLAY_OPERATIONS[0]
    statement, params = operation.prepare(_token(row))
    assert isinstance(statement, Insert)
    assert statement.table is PlayRow.__table__
    assert len(row) == len(PlayRow.__table__.c.keys()) == 41
    assert set(params) == set(row) - {"tenant_id"}
    assert params["event_kind"] == "non_pitch"
    assert params["batting_result_key"] == "batting-result.intentional-walk"
    for name in (
        "pitch_type_key",
        "course_x",
        "course_y",
        "pitch_speed",
        "stance",
        "batting_side",
    ):
        assert params[name] is None
    assert operation.preflight is not None
    preflight = operation.preflight(_token(row), {**params, "tenant_id": IDS[0]})
    assert len(preflight.operations) == 3


@pytest.mark.parametrize(
    "mutation",
    [
        "ordinary-token",
        "fake-pitch",
        "unknown-nonpitch",
        "wrong-result",
        "pitch-type",
        "course-x",
        "course-y",
        "pitch-speed",
        "stance",
        "batting-side",
        "batted-observation",
        "strategy",
        "unknown-column",
    ],
)
def test_only_exact_intentional_walk_nonpitch_row_is_accepted(mutation: str):
    """旧投球資格や未知非投球・観測の仮補完を拒否する。"""
    row = _row()
    kind = PlayPrefixPlayRowInsertToken
    if mutation == "ordinary-token":
        kind = OrdinaryPlayRowInsertToken
    elif mutation == "fake-pitch":
        row["event_kind"] = "pitch"
    elif mutation == "unknown-nonpitch":
        row["batting_result_key"] = "batting-result.unknown"
    elif mutation == "wrong-result":
        row["batting_result_key"] = "batting-result.walk"
    elif mutation == "pitch-type":
        row["pitch_type_key"] = "fastball"
    elif mutation == "course-x":
        row["course_x"] = 0.5
    elif mutation == "course-y":
        row["course_y"] = 0.5
    elif mutation == "pitch-speed":
        row["pitch_speed"] = 100.0
    elif mutation == "stance":
        row["stance"] = "1"
    elif mutation == "batting-side":
        row["batting_side"] = "右"
    elif mutation == "batted-observation":
        row["batted_ball_type"] = "grounder"
    elif mutation == "strategy":
        row["strategy_key"] = "steal"
    else:
        row["unknown"] = True
    with pytest.raises(OrdinaryPlayRowError):
        PLAY_PREFIX_PLAY_OPERATIONS[0].prepare(_token(row, kind))
