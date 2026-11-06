"""同一取引の真正v3原本からP3変更系列を唯一artifactで準備する。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID, uuid5

from pitchlog.domainrt.past_correction_lineup import (
    CorrectedLineupPitch,
    LineupCorrectionUnsupported,
    SavedLineupPitch,
    build_corrected_lineup_payloads,
    evaluate_lineup_pitch_result_correction,
)
from pitchlog.repositories.past_correction_source import (
    PastCorrectionSourceUnavailable,
    read_past_correction_v3_source_snapshot,
)
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.change_path import _target
from pitchlog.sync.idempotency import _json_value
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.past_correction_payload import (
    PastCorrectionPayloadError,
    bind_lineup_pitch_change_payload,
    read_lineup_pitch_change_payload,
)
from pitchlog.sync.past_correction_physical import (
    CorrectedPhysicalPitch,
    prepare_corrected_physical_pitches,
)
from pitchlog.sync.terminal_pitch_payload import LineupPitchPlayPayload


class PastCorrectionPreparationUnavailable(RuntimeError):
    """P3保存前の真正原本・本文・再評価を結べない。"""


@dataclass(frozen=True, slots=True)
class PreparedP3LineupCorrection:
    """同TXにだけ渡す旧原本と訂正後系列。保存・ACKの証明ではない。"""

    capsule_id: UUID
    change_event_id: UUID
    target_generation: int
    target_d1: int
    originals: tuple[SavedLineupPitch, ...]
    corrected: tuple[CorrectedLineupPitch, ...]
    payloads: tuple[LineupPitchPlayPayload, ...]
    physical: tuple[CorrectedPhysicalPitch, ...]


def prepare_p3_lineup_correction(
    scope: _TenantTransaction,
    event: SyncEvent,
    *,
    capsule_id: UUID,
    change_event_id: UUID,
) -> PreparedP3LineupCorrection:
    """対象版検査前に同一scopeの原本を閉じ、T4へ渡す候補を作る。"""
    if (
        type(scope) is not _TenantTransaction
        or type(event) is not SyncEvent
        or event.v5 != "play_change"
        or not isinstance(event.v7, Mapping)
        or type(capsule_id) is not UUID
        or type(change_event_id) is not UUID
        or capsule_id == change_event_id
        or capsule_id == UUID(int=0)
        or change_event_id == UUID(int=0)
    ):
        raise PastCorrectionPreparationUnavailable("P3準備の識別が不正")
    try:
        game_id, generation, target_d1 = _target(event)
        if game_id != UUID(event.game_id):
            raise PastCorrectionPreparationUnavailable("P3対象試合が不一致")
        snapshot = read_past_correction_v3_source_snapshot(scope, game_id, target_d1)
        rows = snapshot.rows
        current = rows[-1].calculation.response.value.next_prefix_ref
        if (
            snapshot.internal_generation != generation
            or current.tenant_id != str(scope._bound_tenant_id)
            or current.game_id != event.game_id
        ):
            raise PastCorrectionPreparationUnavailable("P3原本世代が不一致")
        payload = read_lineup_pitch_change_payload(
            json.dumps(_json_value(event.v7), ensure_ascii=False, allow_nan=False)
        )
        bind_lineup_pitch_change_payload(payload, rows, target_d1, current)
        checkpoint_ids = tuple(
            uuid5(capsule_id, f"checkpoint:{row.source_event_id}")
            for row in rows[target_d1 - 1 :]
        )
        corrected = evaluate_lineup_pitch_result_correction(
            rows,
            payload.replacement_result_id,
            checkpoint_ids,
            target_d1=target_d1,
        )
        payloads = build_corrected_lineup_payloads(
            rows, corrected, payload.replacement_observations
        )
        physical = prepare_corrected_physical_pitches(
            rows,
            corrected,
            payloads,
            tenant_id=scope._bound_tenant_id,
            game_id=game_id,
            capsule_id=capsule_id,
            change_event_id=change_event_id,
        )
        return PreparedP3LineupCorrection(
            capsule_id,
            change_event_id,
            generation,
            target_d1,
            rows,
            corrected,
            payloads,
            physical,
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        PastCorrectionSourceUnavailable,
        PastCorrectionPayloadError,
        LineupCorrectionUnsupported,
    ):
        raise PastCorrectionPreparationUnavailable("P3原本と変更系列が不成立") from None
