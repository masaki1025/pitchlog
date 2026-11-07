"""通常投球P3の閉じた変更本文と真正v3原本への参照照合。"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import Field

from pitchlog.domainrt.first_pitch import _Frozen, _invalid_constant, _unique_object
from pitchlog.domainrt.lineup_play_prefix_continuation import PrefixRef
from pitchlog.domainrt.past_correction_lineup import SavedLineupPitch
from pitchlog.domainrt.play_prefix_continuation import CanonicalUuid
from pitchlog.sync.first_ball_payload import FirstBallObservations


class PastCorrectionPayloadError(ValueError):
    """本文の値や資格を例外へ出さない閉拒否。"""

    def __init__(self) -> None:
        """固定の失敗文を返す。"""
        super().__init__("P3 v3変更本文と原本が一致しません")


class LineupPitchChangePayload(_Frozen):
    """対象の元identity・現在head・新結果/観測だけを明示する。"""

    format_version: Literal["p3-lineup-pitch-change-v1"] = Field(
        alias="formatVersion"
    )
    expected_prefix_ref: PrefixRef = Field(alias="expectedPrefixRef")
    target_event_id: CanonicalUuid = Field(alias="targetEventId")
    target_play_id: CanonicalUuid = Field(alias="targetPlayId")
    original_result_id: Literal[
        "batting-result.ball",
        "batting-result.called-pitch",
        "batting-result.called-strikeout",
    ] = Field(alias="originalResultId")
    replacement_result_id: Literal[
        "batting-result.ball", "batting-result.called-pitch"
    ] = Field(alias="replacementResultId")
    replacement_observations: FirstBallObservations = Field(
        alias="replacementObservations"
    )


def read_lineup_pitch_change_payload(raw: str) -> LineupPitchChangePayload:
    """重複key・未知member・型変換・省略/null補完を拒否する。"""
    if type(raw) is not str or not 1 <= len(raw) <= 50000:
        raise PastCorrectionPayloadError
    try:
        supplied = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        value = LineupPitchChangePayload.model_validate_json(raw)
        if (
            json.dumps(supplied, ensure_ascii=False, sort_keys=True)
            != json.dumps(
                value.model_dump(mode="json", by_alias=True, exclude_unset=True),
                ensure_ascii=False,
                sort_keys=True,
            )
            or type(value.replacement_observations) is not FirstBallObservations
        ):
            raise PastCorrectionPayloadError
        return value
    except (TypeError, ValueError, RecursionError):
        raise PastCorrectionPayloadError from None


def bind_lineup_pitch_change_payload(
    payload: LineupPitchChangePayload,
    rows: tuple[SavedLineupPitch, ...],
    target_d1: int,
    current_prefix_ref: PrefixRef,
) -> None:
    """同TX current原本と対象直前の実identityへ変更本文を束縛する。"""
    if (
        type(payload) is not LineupPitchChangePayload
        or type(rows) is not tuple
        or type(target_d1) is not int
        or not 1 <= target_d1 <= len(rows)
        or type(current_prefix_ref) is not PrefixRef
        or payload.expected_prefix_ref != current_prefix_ref
        or payload.expected_prefix_ref.length != str(len(rows))
    ):
        raise PastCorrectionPayloadError
    bind_lineup_pitch_change_target(
        payload, rows[target_d1 - 1], target_d1, len(rows), current_prefix_ref
    )


def bind_lineup_pitch_change_target(
    payload: LineupPitchChangePayload,
    saved: SavedLineupPitch,
    target_d1: int,
    watermark: int,
    current_prefix_ref: PrefixRef,
) -> None:
    """全履歴を保持せず対象1件と固定headの元参照を照合する。"""
    if (
        type(payload) is not LineupPitchChangePayload
        or type(saved) is not SavedLineupPitch
        or type(target_d1) is not int
        or type(watermark) is not int
        or not 1 <= target_d1 <= watermark
        or type(current_prefix_ref) is not PrefixRef
        or payload.expected_prefix_ref != current_prefix_ref
        or payload.expected_prefix_ref.length != str(watermark)
        or saved.d1 != target_d1
        or saved.payload is None
        or saved.payload.calculation != saved.calculation
        or payload.target_event_id != str(saved.source_event_id)
        or payload.target_play_id != saved.calculation.request.play_identity.play_id
        or payload.original_result_id != saved.calculation.request.t1.result_id
        or payload.expected_prefix_ref.tenant_id
        != saved.calculation.request.prefix_ref.tenant_id
        or payload.expected_prefix_ref.game_id
        != saved.calculation.request.prefix_ref.game_id
        or payload.expected_prefix_ref.generation
        != saved.calculation.request.prefix_ref.generation
    ):
        raise PastCorrectionPayloadError
