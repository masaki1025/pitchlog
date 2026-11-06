"""P3の真正capsule/唯一T5全sourceを同writerの一括DB保存へ渡す。"""

from __future__ import annotations

from uuid import UUID

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.repositories.past_correction_right import _PersistP3ProjectionToken
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.change_path import _target
from pitchlog.sync.control_provider.evidence import D1lessPhaseBinding
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.past_correction_execution import (
    bind_p3_persistence,
    p3_projection_candidate,
)
from pitchlog.sync.ports import PortWriter


class PastCorrectionProjectionError(RuntimeError):
    """P3保存receiptが実frame/current head/T5と一致しない。"""


def project_p3_correction(
    handle: _TenantTransaction, event: SyncEvent, writer: PortWriter
) -> None:
    """T2済み同TXで全投影を保存し、評価集合digestを実候補と照合する。"""
    capsule, stats, source = p3_projection_candidate(handle, event, writer)
    lease = source.bound._lease
    phase = source.phase
    target = _target(event)
    if (
        type(handle) is not _TenantTransaction
        or type(event) is not SyncEvent
        or type(writer) is not PortWriter
        or type(phase) is not D1lessPhaseBinding
        or target != (
            UUID(event.game_id),
            capsule.internal_generation,
            capsule.target_d1,
        )
        or phase.d5 != UUID(event.d5)
        or phase.attempt.tenant_id != handle._bound_tenant_id
        or phase.attempt.game_id != UUID(event.game_id)
        or lease.attempt_id != phase.attempt.attempt_id
        or lease.phase_id != phase.phase_id
        or lease.device_id != phase.attempt.device_id
        or lease.game_id != UUID(event.game_id)
        or stats.capsule_id != capsule.capsule_id
        or len(stats.sources) != len(capsule.items)
    ):
        raise PastCorrectionProjectionError("P3保存元frameが不一致")
    capsule_json = _canonical_json(
        {
            "version": "p3-current-capsule-v1",
            "tenant_id": str(handle._bound_tenant_id),
            "game_id": event.game_id,
            "d5": event.d5,
            "expected_version": event.v11,
            "internal_generation": capsule.internal_generation,
            "target_d1": capsule.target_d1,
            "capsule_id": str(capsule.capsule_id),
            "change_event_id": str(capsule.change_event_id),
            "previous_checkpoint_id": str(capsule.previous_checkpoint_id),
            "previous_checkpoint_revision": capsule.previous_checkpoint_revision,
            "previous_checkpoint_digest": capsule.previous_checkpoint_digest,
            "next_checkpoint": capsule.next_checkpoint.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
            "items": list(capsule.items),
            "source_set_digest": capsule.source_set_digest,
        }
    )
    stats_json = _canonical_json(
        {
            "version": "p3-current-stats-v1",
            "capsule_id": str(stats.capsule_id),
            "model_sha256": stats.model_sha256,
            "evaluation_set_digest": stats.evaluation_set_digest,
            "sources": [
                {
                    "d1": source_item.d1,
                    "original_event_id": str(source_item.original_event_id),
                    "effective_event_id": str(source_item.effective_event_id),
                    "effective_play_row_id": str(source_item.effective_play_row_id),
                    "evaluation": source_item.evaluation,
                    "evaluation_digest": source_item.evaluation_digest,
                }
                for source_item in stats.sources
            ],
        }
    )
    token = _PersistP3ProjectionToken(
        lease.attempt_id,
        lease.phase_id,
        lease.nonce,
        lease.device_id,
        UUID(event.game_id),
        capsule_json,
        stats_json,
    )
    with bind_p3_persistence(handle, event, writer, token):
        result = handle.run_function(token)
    if (
        type(result) is not TenantOperationResult
        or type(result.rows) is not tuple
        or len(result.rows) != 1
        or type(result.rows[0]) is not tuple
        or len(result.rows[0]) != 4
        or result.rows[0][0] != capsule.capsule_id
        or result.rows[0][1] != capsule.next_checkpoint.content_digest
        or result.rows[0][2] != stats.evaluation_set_digest
        or type(result.rows[0][3]) is not UUID
        or result.rows[0][3] == UUID(int=0)
    ):
        raise PastCorrectionProjectionError("P3保存receiptが全候補と不一致")
    source.read(handle, event)
