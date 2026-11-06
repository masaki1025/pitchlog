"""真正非投球入力を既v3保存行の物理形へ写す境界。"""

from __future__ import annotations

from uuid import UUID

from pitchlog.db.game_state.models import PlayRow
from pitchlog.repositories.first_ball_operations import _NULL_COLUMNS
from pitchlog.sync.nonpitch_payload import IntentionalWalkObservations
from pitchlog.sync.ordinary_pitch_payload import OrdinaryPitchParticipants


def intentional_walk_physical_row(
    observation: IntentionalWalkObservations,
    people: OrdinaryPitchParticipants,
    result_id: str,
    *,
    tenant_id: UUID,
    game_id: UUID,
    source_event_id: UUID,
    row_id: UUID,
    play_number: int,
) -> dict[str, object]:
    """投球観測を仮補完せず、41列の非投球PlayRowを作る。"""
    if (
        type(observation) is not IntentionalWalkObservations
        or type(people) is not OrdinaryPitchParticipants
        or type(result_id) is not str
        or result_id != "batting-result.intentional-walk"
        or any(
            type(value) is not UUID
            for value in (tenant_id, game_id, source_event_id, row_id)
        )
        or type(play_number) is not int
        or play_number < 1
    ):
        raise ValueError("申告敬遠の物理入力が不正")
    row = {
        **dict.fromkeys(_NULL_COLUMNS),
        "tenant_id": str(tenant_id),
        "id": str(row_id),
        "game_id": str(game_id),
        "source_event_id": str(source_event_id),
        "play_number": play_number,
        "batting_order": int(people.batting_order),
        "event_kind": "non_pitch",
        "batting_result_key": result_id,
        "version": 1,
        "migration_unverified": False,
        "batter_id": people.batter_id,
        "pitcher_id": people.pitcher_id,
        "catcher_id": people.catcher_id,
        "batting_side": None,
        "course_x": None,
        "course_y": None,
        "pitch_speed": None,
        "pitch_type_key": None,
        "stance": None,
    }
    if set(row) != set(PlayRow.__table__.c.keys()):
        raise ValueError("非投球の物理列集合が不一致")
    return row
