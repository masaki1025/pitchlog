"""P3の元identityと有効投影を全D1へ閉じたcapsule候補にする。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pitchlog.domainrt.past_correction_lineup import (
    CorrectedLineupPitch,
    SavedLineupPitch,
)
from pitchlog.repositories.play_prefix import LineupPrefixDocument
from pitchlog.sync.idempotency import _json_value, source_fingerprint
from pitchlog.sync.past_correction_checkpoint import build_corrected_lineup_checkpoint
from pitchlog.sync.past_correction_physical import CorrectedPhysicalPitch
from pitchlog.sync.past_correction_preparation import PreparedP3LineupCorrection
from pitchlog.sync.terminal_pitch_payload import LineupPitchPlayPayload

# item_digestはDB固定列だけを覆う。実効frame再構成用の派生keyは含めない。
P3_ITEM_DERIVED_KEYS = frozenset(
    {"digest", "original_source", "original_event_d2"}
)


def p3_item_digest_source(item: dict[str, object]) -> dict[str, object]:
    """item_digestが覆うDB固定列だけを返す。"""
    return {
        key: value
        for key, value in item.items()
        if key not in P3_ITEM_DERIVED_KEYS
    }


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
    previous_checkpoint: LineupPrefixDocument
    next_checkpoint: LineupPrefixDocument
    items: tuple[dict[str, object], ...]
    source_set_digest: str


def build_p3_current_item(
    saved: SavedLineupPitch,
    *,
    target_d1: int,
    change_event_id: UUID,
    checkpoint: LineupPrefixDocument,
    frame: CorrectedLineupPitch | None,
    payload: LineupPitchPlayPayload | None,
    projected: CorrectedPhysicalPitch | None,
) -> dict[str, object]:
    """元1件と同位置の唯一結果を既capsule完全itemへ束縛する。"""
    if (
        type(saved) is not SavedLineupPitch
        or type(target_d1) is not int
        or target_d1 < 1
        or type(change_event_id) is not UUID
        or type(checkpoint) is not LineupPrefixDocument
        or type(saved.play_row) is not dict
        or type(saved.play_row.get("id")) is not str
        or type(saved.payload) is not LineupPitchPlayPayload
        or type(saved.play_runners) is not tuple
    ):
        raise PastCorrectionCapsuleError("P3元履歴の全原本が不正")
    old_id = saved.play_row["id"]
    if type(old_id) is not str:
        raise PastCorrectionCapsuleError("P3元物理行IDが不正")
    try:
        old_uuid = UUID(old_id)
    except ValueError:
        raise PastCorrectionCapsuleError("P3元物理行IDが不正") from None
    if saved.d1 < target_d1:
        if frame is not None or payload is not None or projected is not None:
            raise PastCorrectionCapsuleError("P3先行位置に訂正候補が混入")
        active_payload = saved.payload
        row = saved.play_row
        runners = list(saved.play_runners)
        effective_event_id = saved.source_event_id
        state = "unchanged"
        entry = saved.calculation.response.value.new_history_entry
    else:
        if (
            type(frame) is not CorrectedLineupPitch
            or type(payload) is not LineupPitchPlayPayload
            or type(projected) is not CorrectedPhysicalPitch
            or frame.d1 != saved.d1
            or frame.source_event_id != saved.source_event_id
            or projected.original_event_id != saved.source_event_id
            or projected.original_play_row_id != old_uuid
            or projected.play_row.get("id") != str(projected.new_play_row_id)
            or payload.calculation.request != frame.corrected_request
            or payload.calculation.response != frame.corrected_response
        ):
            raise PastCorrectionCapsuleError("P3訂正後元参照又は計算が不一致")
        active_payload = payload
        row = projected.play_row
        runners = list(projected.play_runners)
        effective_event_id = projected.effective_event_id
        state = "corrected"
        entry = frame.corrected_response.value.new_history_entry
    if (
        (saved.d1 == target_d1 and effective_event_id != change_event_id)
        or (saved.d1 != target_d1 and effective_event_id != saved.source_event_id)
        or row.get("tenant_id") != checkpoint.prefix_ref.tenant_id
        or row.get("game_id") != checkpoint.prefix_ref.game_id
        or row.get("source_event_id") != str(effective_event_id)
    ):
        raise PastCorrectionCapsuleError("P3有効物理行のscopeが不一致")
    original_entry = saved.calculation.response.value.new_history_entry
    item: dict[str, object] = {
        "d1": saved.d1,
        "d2": saved.d2,
        "state": state,
        "original_event_id": str(saved.source_event_id),
        "effective_event_id": str(effective_event_id),
        "original_play_row_id": old_id,
        "effective_play_row_id": row["id"],
        "original_payload": saved.payload.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        ),
        "original_history_entry": original_entry.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        ),
        "original_play_row": _json_value(saved.play_row),
        "original_play_runners": _json_value(list(saved.play_runners)),
        "payload": active_payload.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        ),
        "history_entry": entry.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        ),
        "play_row": _json_value(row),
        "play_runners": _json_value(runners),
    }
    item["digest"] = source_fingerprint(item)
    return item


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
        if saved.d1 != index:
            raise PastCorrectionCapsuleError("P3元履歴の順序が不正")
        items.append(
            build_p3_current_item(
                saved,
                target_d1=prepared.target_d1,
                change_event_id=prepared.change_event_id,
                checkpoint=prepared.original_checkpoint,
                frame=corrected.get(index),
                payload=payloads.get(index),
                projected=physical.get(index),
            )
        )
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
        prepared.original_checkpoint,
        checkpoint,
        tuple(items),
        source_set_digest,
    )
