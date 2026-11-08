"""P3の真正capsule/唯一T5全sourceを同writerの一括DB保存へ渡す。"""

from __future__ import annotations

from uuid import UUID

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.repositories.past_correction_paged_tokens import (
    _AppendP3ProjectionPageToken,
    _BeginP3ProjectionPageToken,
    _FinalizeP3ProjectionPageToken,
)
from pitchlog.repositories.past_correction_right import _PersistP3ProjectionToken
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH
from pitchlog.sync.change_path import _bound_target
from pitchlog.sync.control_provider.evidence import D1lessPhaseBinding
from pitchlog.sync.idempotency import operation_fingerprint
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.past_correction_execution import (
    bind_p3_paged_persistence,
    bind_p3_persistence,
    p3_paged_projection_candidate,
    p3_projection_candidate,
)
from pitchlog.sync.past_correction_paged import (
    P3PagedPreparationProof,
    PreparedP3Page,
    _chain_step,
    visit_p3_lineup_correction_pages,
)
from pitchlog.sync.play_export_p3_producer import (
    persist_p3_play_exports,
    prepare_p3_play_export_anchor,
)
from pitchlog.sync.play_export_producer import PlayExportWriterUnavailable
from pitchlog.sync.ports import PortWriter
from pitchlog.sync.source_binding import _E1CoreSource


class PastCorrectionProjectionError(RuntimeError):
    """P3保存receiptが実frame/current head/T5と一致しない。"""


def _prepare_p3_csv_prior(handle, event, writer):
    """新しいCSV原本不足だけを既P3の閉503へ写し、全取消の例外を保つ。"""
    try:
        return prepare_p3_play_export_anchor(handle, event, writer)
    except PlayExportWriterUnavailable as error:
        raise PastCorrectionProjectionError("P3 CSV保存前原本が未供給") from error


def _persist_p3_csv(handle, event, writer, prior):
    """保存後原本の失敗も同TXのP3失敗として伝播させる。"""
    try:
        persist_p3_play_exports(handle, event, writer, prior)
    except PlayExportWriterUnavailable as error:
        raise PastCorrectionProjectionError("P3 CSV完成原本が未供給") from error


def _project_p3_paged_correction(
    handle: _TenantTransaction,
    event: SyncEvent,
    writer: PortWriter,
    proof: P3PagedPreparationProof,
    source: _E1CoreSource,
) -> None:
    """第一走sealと第二走の各頁を同TXへ保存し、最後だけ公開する。"""
    if type(proof) is not P3PagedPreparationProof or proof.watermark <= 25:
        raise PastCorrectionProjectionError("P3頁保存の元sealが不正")
    actual_source = p3_paged_projection_candidate(handle, event, writer)
    if (
        actual_source is None
        or actual_source[0] is not proof
        or actual_source[1] is not source
    ):
        raise PastCorrectionProjectionError("P3頁保存の実frameが不一致")
    lease = source.bound._lease
    phase = source.phase
    target = _bound_target(handle, event, source)[:3]
    if (
        type(phase) is not D1lessPhaseBinding
        or target != (UUID(event.game_id), proof.internal_generation, proof.target.d1)
        or phase.d5 != UUID(event.d5)
        or phase.attempt.tenant_id != handle._bound_tenant_id
        or phase.attempt.game_id != UUID(event.game_id)
        or lease.attempt_id != phase.attempt.attempt_id
        or lease.phase_id != phase.phase_id
        or lease.device_id != phase.attempt.device_id
        or lease.game_id != UUID(event.game_id)
        or event.v11 != 1
    ):
        raise PastCorrectionProjectionError("P3頁保存の実資格が不一致")
    # UUIDは実frameで先に発行したものだけを使用する。
    from pitchlog.sync.past_correction_execution import p3_paged_ids

    capsule_id, change_event_id = p3_paged_ids(handle, event, writer)
    original = proof.checkpoint.model_dump(
        mode="json", by_alias=True, exclude_unset=True
    )
    corrected = proof.next_checkpoint.model_dump(
        mode="json", by_alias=True, exclude_unset=True
    )
    capsule_header = _canonical_json(
        {
            "version": "p3-current-capsule-page-v2",
            "tenant_id": str(handle._bound_tenant_id),
            "game_id": event.game_id,
            "d5": event.d5,
            "ledger_fingerprint": operation_fingerprint(event, "P3", None),
            "internal_generation": proof.internal_generation,
            "target_d1": proof.target.d1,
            "capsule_id": str(capsule_id),
            "change_event_id": str(change_event_id),
            "previous_checkpoint_id": proof.checkpoint.id,
            "previous_checkpoint_revision": proof.checkpoint.revision,
            "previous_checkpoint_digest": proof.checkpoint.content_digest,
            "previous_checkpoint": original,
            "next_checkpoint": corrected,
            "watermark": proof.watermark,
            "digest_format": proof.digest_format,
            "item_chain": proof.source_chain,
            "page_seal": proof.page_seal,
            "source_set_digest": proof.source_set_digest,
        }
    )
    stats_header = _canonical_json(
        {
            "version": "p3-current-stats-page-v2",
            "capsule_id": str(capsule_id),
            "model_sha256": SOURCE_MODEL_HASH,
            "evaluation_chain": proof.evaluation_chain,
            "evaluation_set_digest": proof.evaluation_set_digest,
        }
    )
    common = (lease.attempt_id, lease.phase_id, lease.nonce, lease.device_id)
    game_id = UUID(event.game_id)
    begin = _BeginP3ProjectionPageToken(*common, game_id, capsule_header, stats_header)
    with bind_p3_paged_persistence(handle, event, writer, begin):
        started = handle.run_function(begin)
    if type(started) is not TenantOperationResult or started.rows != (
        (capsule_id, proof.watermark),
    ):
        raise PastCorrectionProjectionError("P3頁開始receiptが不一致")
    page_count = 0
    last_d1 = 0
    source_chain = "0" * 64
    evaluation_chain = "0" * 64

    def append(page: PreparedP3Page) -> None:
        """唯一評価済みの25行以下だけを逐次保存する。"""
        nonlocal page_count, last_d1, source_chain, evaluation_chain
        if (
            type(page) is not PreparedP3Page
            or not 1 <= len(page.items) <= 25
            or len(page.items) != len(page.stats_sources)
        ):
            raise PastCorrectionProjectionError("P3頁追記の閉形が不正")
        members = []
        for item, evaluated in zip(page.items, page.stats_sources, strict=True):
            if type(item) is not dict or item.get("d1") != last_d1 + 1:
                raise PastCorrectionProjectionError("P3頁追記の位置が不正")
            item_digest = item.get("digest")
            if type(item_digest) is not str or evaluated.d1 != last_d1 + 1:
                raise PastCorrectionProjectionError("P3頁追記の評価が不一致")
            last_d1 += 1
            source_chain = _chain_step(source_chain, last_d1, item_digest)
            evaluation_chain = _chain_step(
                evaluation_chain,
                last_d1,
                evaluated.original_evaluation_digest,
                evaluated.evaluation_digest,
            )
            members.append(
                {
                    "item": item,
                    "source": {
                        "d1": evaluated.d1,
                        "original_event_id": str(evaluated.original_event_id),
                        "effective_event_id": str(evaluated.effective_event_id),
                        "effective_play_row_id": str(evaluated.effective_play_row_id),
                        "original_evaluation": evaluated.original_evaluation,
                        "original_evaluation_digest": (
                            evaluated.original_evaluation_digest
                        ),
                        "evaluation": evaluated.evaluation,
                        "evaluation_digest": evaluated.evaluation_digest,
                    },
                }
            )
        token = _AppendP3ProjectionPageToken(
            *common, game_id, capsule_id, _canonical_json(members)
        )
        with bind_p3_paged_persistence(handle, event, writer, token):
            receipt = handle.run_function(token)
        if type(receipt) is not TenantOperationResult or receipt.rows != (
            (last_d1, source_chain, evaluation_chain),
        ):
            raise PastCorrectionProjectionError("P3頁追記receiptが不一致")
        page_count += 1

    revisited = visit_p3_lineup_correction_pages(
        handle,
        event,
        capsule_id=capsule_id,
        change_event_id=change_event_id,
        bound_source=source,
        consume=append,
    )
    if (
        revisited != proof
        or page_count != proof.page_count
        or last_d1 != proof.watermark
        or source_chain != proof.source_chain
        or evaluation_chain != proof.evaluation_chain
    ):
        raise PastCorrectionProjectionError("P3頁の二走sealが不一致")
    final = _FinalizeP3ProjectionPageToken(*common, game_id, capsule_id)
    csv_prior = _prepare_p3_csv_prior(handle, event, writer)
    with bind_p3_paged_persistence(handle, event, writer, final):
        receipt = handle.run_function(final)
    if (
        type(receipt) is not TenantOperationResult
        or len(receipt.rows) != 1
        or len(receipt.rows[0]) != 4
        or receipt.rows[0][0] != capsule_id
        or receipt.rows[0][1] != proof.next_checkpoint.content_digest
        or receipt.rows[0][2] != proof.evaluation_set_digest
        or type(receipt.rows[0][3]) is not UUID
        or receipt.rows[0][3].int == 0
    ):
        raise PastCorrectionProjectionError("P3頁確定receiptが不一致")
    _persist_p3_csv(handle, event, writer, csv_prior)
    source.read(handle, event)


def project_p3_correction(
    handle: _TenantTransaction, event: SyncEvent, writer: PortWriter
) -> None:
    """T2済み同TXで全投影を保存し、評価集合digestを実候補と照合する。"""
    paged = p3_paged_projection_candidate(handle, event, writer)
    if paged is not None:
        _project_p3_paged_correction(handle, event, writer, *paged)
        return
    capsule, stats, source = p3_projection_candidate(handle, event, writer)
    lease = source.bound._lease
    phase = source.phase
    target = _bound_target(handle, event, source)[:3]
    if (
        type(handle) is not _TenantTransaction
        or type(event) is not SyncEvent
        or type(writer) is not PortWriter
        or type(phase) is not D1lessPhaseBinding
        or target
        != (
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
            "ledger_fingerprint": operation_fingerprint(event, "P3", None),
            "expected_version": event.v11,
            "internal_generation": capsule.internal_generation,
            "target_d1": capsule.target_d1,
            "capsule_id": str(capsule.capsule_id),
            "change_event_id": str(capsule.change_event_id),
            "previous_checkpoint_id": str(capsule.previous_checkpoint_id),
            "previous_checkpoint_revision": capsule.previous_checkpoint_revision,
            "previous_checkpoint_digest": capsule.previous_checkpoint_digest,
            "previous_checkpoint": capsule.previous_checkpoint.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
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
                    "original_evaluation": source_item.original_evaluation,
                    "original_evaluation_digest": (
                        source_item.original_evaluation_digest
                    ),
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
    csv_prior = _prepare_p3_csv_prior(handle, event, writer)
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
    _persist_p3_csv(handle, event, writer, csv_prior)
    source.read(handle, event)
