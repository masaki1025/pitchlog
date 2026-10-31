"""通常投球の実観測を全41物理列へ写す単一mapper。資格や数学は生成しない。"""

from uuid import UUID

from pitchlog.db.game_state.models import PlayRow
from pitchlog.repositories.first_ball_operations import _NULL_COLUMNS
from pitchlog.sync.first_ball_course import course_unit_to_double
from pitchlog.sync.ordinary_pitch_payload import OrdinaryPitchPlayPayload


def ordinary_pitch_physical_row(
    payload: OrdinaryPitchPlayPayload,
    *,
    tenant_id: UUID,
    game_id: UUID,
    source_event_id: UUID,
    row_id: UUID,
    play_number: int,
) -> dict[str, object]:
    """実payloadと独立した原本参照からだけ保存列を構成する。"""
    if type(payload) is not OrdinaryPitchPlayPayload:
        raise ValueError("通常payloadの実型が必要")
    return pitch_physical_row(
        payload.observations,
        payload.participants,
        payload.calculation.request.t1.result_id,
        tenant_id=tenant_id,
        game_id=game_id,
        source_event_id=source_event_id,
        row_id=row_id,
        play_number=play_number,
    )


def pitch_physical_row(
    observations,
    people,
    result_id,
    *,
    tenant_id,
    game_id,
    source_event_id,
    row_id,
    play_number,
):
    """旧v1/v2の実観測を同じ全41列mapperへ渡す。数学は再計算しない。"""
    from pitchlog.sync.first_ball_payload import FirstBallObservations
    from pitchlog.sync.ordinary_pitch_payload import OrdinaryPitchParticipants

    if (
        type(observations) is not FirstBallObservations
        or type(people) is not OrdinaryPitchParticipants
        or type(result_id) is not str
    ):
        raise ValueError("物理mapperの実型が不正")
    speed = observations.pitch_speed.kmh
    row = {
        **dict.fromkeys(_NULL_COLUMNS),
        "tenant_id": str(tenant_id),
        "id": str(row_id),
        "game_id": str(game_id),
        "source_event_id": str(source_event_id),
        "play_number": play_number,
        "batting_order": int(people.batting_order),
        "event_kind": "pitch",
        "batting_result_key": result_id,
        "version": 1,
        "migration_unverified": False,
        "batter_id": people.batter_id,
        "pitcher_id": people.pitcher_id,
        "catcher_id": people.catcher_id,
        "pitch_type_key": observations.pitch_type_key,
        "course_x": course_unit_to_double(observations.course.x),
        "course_y": course_unit_to_double(observations.course.y),
        "pitch_speed": None if speed is None else float(speed),
        "stance": observations.stance,
        "batting_side": observations.batting_side,
    }
    if set(row) != set(PlayRow.__table__.c.keys()):
        raise ValueError("物理列集合が不一致")
    return row
