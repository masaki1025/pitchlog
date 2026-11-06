"""P3の元identityと有効投影を全D1へ閉じたcapsule候補にする。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pitchlog.repositories.play_prefix import LineupPrefixDocument
from pitchlog.sync.idempotency import _json_value, source_fingerprint
from pitchlog.sync.past_correction_checkpoint import build_corrected_lineup_checkpoint
from pitchlog.sync.past_correction_preparation import PreparedP3LineupCorrection
from pitchlog.sync.terminal_pitch_payload import LineupPitchPlayPayload


class PastCorrectionCapsuleError(RuntimeError):
    """全履歴の有効投影を曖昧なく固定できない。"""


@dataclass(frozen=True, slots=True)
class P3CurrentCapsule:
    """同一取引内の保存候補。DB書込資格・公開headではない。"""

    capsule_id: UUID
    change_event_id: UUID
    internal_generation: int
    target_d1: int
    previous_checkpoint_id: UUID
    previous_checkpoint_revision: int
    previous_checkpoint_digest: str
    next_checkpoint: LineupPrefixDocument
    items: tuple[dict[str, object], ...]
    source_set_digest: str


def build_p3_current_capsule(
    prepared: PreparedP3LineupCorrection,
) -> P3CurrentCapsule:
    """元D1/D2/数学identityを保持し有効V7/物理列の全版を記す。"""
    if (
        type(prepared) is not PreparedP3LineupCorrection
        or type(prepared.original_checkpoint) is not LineupPrefixDocument
        or len(prepared.originals) < 1
        or prepared.target_generation
        != int(prepared.original_checkpoint.internal_generation)
        or not 1 <= prepared.target_d1 <= len(prepared.originals) <= 25
        or len(
            {
                len(prepared.corrected),
                len(prepared.payloads),
                len(prepared.physical),
                len(prepared.originals) - prepared.target_d1 + 1,
            }
        ) != 1
    ):
        raise PastCorrectionCapsuleError("P3全履歴の範囲が不一致")
    checkpoint = build_corrected_lineup_checkpoint(prepared)
    corrected = {row.d1: row for row in prepared.corrected}
    payloads = {
        row.d1: payload
        for row, payload in zip(prepared.corrected, prepared.payloads, strict=True)
    }
    physical = {row.d1: row for row in prepared.physical}
    if any(
        len(values) != len(prepared.corrected)
        for values in (corrected, payloads, physical)
    ):
        raise PastCorrectionCapsuleError("P3訂正後位置が重複")
    items: list[dict[str, object]] = []
    for index, saved in enumerate(prepared.originals, start=1):
        if (
            saved.d1 != index
            or type(saved.play_row) is not dict
            or type(saved.play_row.get("id")) is not str
        ):
            raise PastCorrectionCapsuleError("P3元履歴の位置又は物理原本が不正")
        old_id = saved.play_row["id"]
        if type(old_id) is not str:
            raise PastCorrectionCapsuleError("P3元物理行IDが不正")
        try:
            old_uuid = UUID(old_id)
        except ValueError:
            raise PastCorrectionCapsuleError("P3元物理行IDが不正") from None
        if index < prepared.target_d1:
            if (
                type(saved.payload) is not LineupPitchPlayPayload
                or saved.play_runners is None
            ):
                raise PastCorrectionCapsuleError("P3先行履歴の全原本が欠落")
            payload = saved.payload
            row = saved.play_row
            runners = list(saved.play_runners)
            effective_event_id = saved.source_event_id
            state = "unchanged"
            entry = saved.calculation.response.value.new_history_entry
        else:
            frame = corrected.get(index)
            payload = payloads.get(index)
            projected = physical.get(index)
            if (
                frame is None
                or payload is None
                or projected is None
                or frame.source_event_id != saved.source_event_id
                or projected.original_event_id != saved.source_event_id
                or projected.original_play_row_id != old_uuid
                or type(payload) is not LineupPitchPlayPayload
                or projected.play_row.get("id") != str(projected.new_play_row_id)
                or payload.calculation.request != frame.corrected_request
                or payload.calculation.response != frame.corrected_response
            ):
                raise PastCorrectionCapsuleError("P3訂正後元参照又は計算が不一致")
            row = projected.play_row
            runners = list(projected.play_runners)
            effective_event_id = projected.effective_event_id
            state = "corrected"
            entry = frame.corrected_response.value.new_history_entry
        if (
            row.get("tenant_id")
            != str(prepared.original_checkpoint.prefix_ref.tenant_id)
            or row.get("game_id")
            != str(prepared.original_checkpoint.prefix_ref.game_id)
            or row.get("source_event_id") != str(effective_event_id)
        ):
            raise PastCorrectionCapsuleError("P3有効物理行のscopeが不一致")
        item = {
            "d1": index,
            "d2": saved.d2,
            "state": state,
            "original_event_id": str(saved.source_event_id),
            "effective_event_id": str(effective_event_id),
            "original_play_row_id": old_id,
            "effective_play_row_id": row["id"],
            "payload": payload.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
            "history_entry": entry.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
            "play_row": _json_value(row),
            "play_runners": _json_value(runners),
        }
        item["digest"] = source_fingerprint(item)
        items.append(item)
    if (
        items[prepared.target_d1 - 1]["effective_event_id"]
        != str(prepared.change_event_id)
        or any(
            item["effective_event_id"] != item["original_event_id"]
            for item in items[: prepared.target_d1 - 1]
            + items[prepared.target_d1 :]
        )
    ):
        raise PastCorrectionCapsuleError("P3対象/後続のeffective eventが不一致")
    source_set_digest = source_fingerprint(
        {
            "capsule_id": str(prepared.capsule_id),
            "change_event_id": str(prepared.change_event_id),
            "old_checkpoint_digest": prepared.original_checkpoint.content_digest,
            "new_checkpoint_digest": checkpoint.content_digest,
            "item_digests": [item["digest"] for item in items],
        }
    )
    return P3CurrentCapsule(
        prepared.capsule_id,
        prepared.change_event_id,
        prepared.target_generation,
        prepared.target_d1,
        UUID(prepared.original_checkpoint.id),
        int(prepared.original_checkpoint.revision),
        prepared.original_checkpoint.content_digest,
        checkpoint,
        tuple(items),
        source_set_digest,
    )
