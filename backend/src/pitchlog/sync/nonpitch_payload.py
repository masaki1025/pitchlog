"""申告敬遠の観測不要V7を既v3一回計算へ閉じて結合する。"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.domainrt.first_pitch import _Frozen
from pitchlog.domainrt.first_pitch_continuation import _check_frozen_members


class IntentionalWalkObservations(_Frozen):
    """投球コースや球種を補わない明示非投球タグ。"""

    kind: Literal["intentional-walk"] = Field(alias="kind")


def require_intentional_walk_observation(t1: object, observation: object) -> None:
    """観測タグと数学要求の操作種別だけを照合し、野球値を再計算しない。"""
    from pitchlog.domainrt.lineup_play_prefix_continuation import T1Input

    if (
        type(t1) is not T1Input
        or type(observation) is not IntentionalWalkObservations
        or t1.event_kind != "batting-result"
        or t1.result_id != "batting-result.intentional-walk"
        or t1.pitch_event_kind != "non-pitch-event"
    ):
        raise ValueError("申告敬遠の閉入力ではありません")
    _check_frozen_members(t1)
    _check_frozen_members(observation)


def format_intentional_walk_prefix_payload(calculation: object) -> tuple[str, str]:
    """実一回計算の全値をV7/V8へ写し、投球観測や成功資格を作らない。"""
    from pitchlog.sync.terminal_pitch_payload import (
        LineupPitchCalculation,
        LineupPitchPlayPayload,
        read_lineup_pitch_payload,
    )

    if type(calculation) is not LineupPitchCalculation:
        raise ValueError("v3実計算が必要です")
    _check_frozen_members(calculation)
    require_intentional_walk_observation(
        calculation.request.t1, IntentionalWalkObservations(kind="intentional-walk")
    )
    raw_v7 = _canonical_json(
        {
            "formatVersion": "play-prefix-play-v3",
            "observations": {"kind": "intentional-walk"},
            "participants": calculation.response.value.before_participants.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
            "calculation": calculation.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
        }
    )
    raw_v8 = _canonical_json(
        calculation.response.value.new_history_entry.difference.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        )
    )
    LineupPitchPlayPayload.model_validate_json(raw_v7)
    read_lineup_pitch_payload(raw_v7, raw_v8, expected_calculation=calculation)
    return raw_v7, raw_v8
