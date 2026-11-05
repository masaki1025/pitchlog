"""通常投球の実観測を全41物理列へ写す単一mapper。資格や数学は生成しない。"""

import math
from decimal import Decimal, InvalidOperation
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
    from pitchlog.sync.terminal_pitch_payload import BattedHitPlayObservations

    if (
        type(observations) not in {FirstBallObservations, BattedHitPlayObservations}
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
    if type(observations) is BattedHitPlayObservations:
        if observations.result_id != result_id:
            raise ValueError("打球の結果原本が不一致")
        ball = observations.batted_ball
        row.update(
            {
                "raw_fielder_position": ball.raw_fielder_position,
                "resolved_fielder_id": ball.resolved_fielder_id,
                "batted_ball_type": ball.type_key,
                "batted_ball_strength": ball.strength_key,
                "hit_x": _observed_storage_unit(ball.hit_x),
                "hit_y": _observed_storage_unit(ball.hit_y),
            }
        )
    if set(row) != set(PlayRow.__table__.c.keys()):
        raise ValueError("物理列集合が不一致")
    return row


def _observed_storage_unit(value: str | None) -> float | None:
    """既保存単位0..1の観測をDoubleへ束縛する。画面座標の変換をしない。"""
    if value is None:
        return None
    if type(value) is not str:
        raise ValueError("打球保存座標は明示十進文字列が必要")
    try:
        decimal = Decimal(value)
        if not decimal.is_finite() or not Decimal(0) <= decimal <= Decimal(1):
            raise ValueError("打球保存座標が0..1の有限値ではない")
        result = float(value)
    except (InvalidOperation, OverflowError):
        raise ValueError("打球保存座標の表現が不正") from None
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError("打球保存座標がDoubleの範囲外")
    return result
