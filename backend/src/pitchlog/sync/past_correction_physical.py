"""P3訂正系列の物理投影候補を既単一mapperで作る。保存資格は発行しない。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid5

from pitchlog.domainrt.past_correction_lineup import (
    CorrectedLineupPitch,
    LineupCorrectionUnsupported,
    SavedLineupPitch,
)
from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
from pitchlog.sync.terminal_pitch_payload import LineupPitchPlayPayload
from pitchlog.sync.terminal_pitch_projection import runner_physical_rows


@dataclass(frozen=True, slots=True)
class CorrectedPhysicalPitch:
    """元identityと有効投影。DB保存・current選択は別の資格。"""

    original_event_id: UUID
    effective_event_id: UUID
    d1: int
    d2: int
    original_play_row_id: UUID
    play_identity_id: UUID
    new_play_row_id: UUID
    play_row: dict[str, object]
    play_runners: tuple[dict[str, object], ...]


def prepare_corrected_physical_pitches(
    rows: tuple[SavedLineupPitch, ...],
    corrected: tuple[CorrectedLineupPitch, ...],
    payloads: tuple[LineupPitchPlayPayload, ...],
    *,
    tenant_id: UUID,
    game_id: UUID,
    capsule_id: UUID,
    change_event_id: UUID,
    target_d1: int | None = None,
) -> tuple[CorrectedPhysicalPitch, ...]:
    """対象は別行PKで作り、後続は全値一致する元行だけ再利用する。"""
    if (
        type(rows) is not tuple
        or type(corrected) is not tuple
        or type(payloads) is not tuple
        or not corrected
        or len(corrected) != len(payloads)
        or any(
            type(value) is not UUID
            for value in (tenant_id, game_id, capsule_id, change_event_id)
        )
        or (target_d1 is not None and (type(target_d1) is not int or target_d1 < 1))
    ):
        raise LineupCorrectionUnsupported("訂正v3物理系列の入力が不正")
    target_position = corrected[0].d1 if target_d1 is None else target_d1
    if target_position > corrected[-1].d1:
        raise LineupCorrectionUnsupported("訂正v3物理対象がページ末尾を超過")
    by_d1 = {row.d1: row for row in rows}
    if len(by_d1) != len(rows):
        raise LineupCorrectionUnsupported("訂正v3物理原本の位置が重複")
    result: list[CorrectedPhysicalPitch] = []
    for frame, payload in zip(corrected, payloads, strict=True):
        saved = by_d1.get(frame.d1)
        if (
            type(frame) is not CorrectedLineupPitch
            or type(payload) is not LineupPitchPlayPayload
            or type(saved) is not SavedLineupPitch
            or type(saved.play_row) is not dict
            or saved.source_event_id != frame.source_event_id
            or saved.d2 != frame.d2
            or payload.calculation.request != frame.corrected_request
            or payload.calculation.response != frame.corrected_response
        ):
            raise LineupCorrectionUnsupported("訂正v3物理系列と計算原本が不一致")
        old = saved.play_row
        old_id, play_number = old.get("id"), old.get("play_number")
        if (
            type(old_id) is not str
            or type(play_number) is not int
            or play_number < 1
            or old.get("source_event_id") != str(saved.source_event_id)
            or old.get("tenant_id") != str(tenant_id)
            or old.get("game_id") != str(game_id)
        ):
            raise LineupCorrectionUnsupported("訂正v3元物理行の参照が不正")
        try:
            original_play_row_id = UUID(old_id)
            play_identity_id = UUID(frame.corrected_request.play_identity.play_id)
        except ValueError:
            raise LineupCorrectionUnsupported("訂正v3元物理行IDが不正") from None
        if play_identity_id != original_play_row_id:
            raise LineupCorrectionUnsupported("訂正v3元play identityが不一致")
        target = frame.d1 == target_position
        new_play_row_id = (
            uuid5(capsule_id, f"play:{saved.source_event_id}")
            if target
            else original_play_row_id
        )
        effective_event_id = change_event_id if target else saved.source_event_id
        physical = pitch_physical_row(
            payload.observations,
            payload.participants,
            frame.corrected_request.t1.result_id,
            tenant_id=tenant_id,
            game_id=game_id,
            source_event_id=effective_event_id,
            row_id=new_play_row_id,
            play_number=play_number,
        )
        runners = runner_physical_rows(
            frame.corrected_request.source.runners,
            t1=frame.corrected_response.value.t1,
            t1_input=frame.corrected_request.t1,
            tenant_id=tenant_id,
            play_id=new_play_row_id,
        )
        if target and runners:
            raise LineupCorrectionUnsupported("P3走者物理投影の保存は未接続")
        if not target and (
            saved.play_runners is None
            or physical != saved.play_row
            or tuple(runners) != saved.play_runners
        ):
            # 元eventの物理行を増やすと旧readerの一件性が破れる。将来の
            # 全置換selector導入までは、同じ物理行に帰着する後続だけ受ける。
            raise LineupCorrectionUnsupported("P3後続物理行の置換は未接続")
        result.append(
            CorrectedPhysicalPitch(
                saved.source_event_id,
                effective_event_id,
                saved.d1,
                saved.d2,
                original_play_row_id,
                play_identity_id,
                new_play_row_id,
                physical,
                tuple(runners),
            )
        )
    return tuple(result)
