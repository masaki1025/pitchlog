"""P3の真正E1 source・同writer・有限v3再評価を同scopeへ閉じる。"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from typing import Iterator, cast
from uuid import UUID, uuid4

from pitchlog.repositories import transaction
from pitchlog.repositories.past_correction_source import (
    read_past_correction_watermark,
)
from pitchlog.repositories.play_prefix import LineupPrefixDocument
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.past_correction_capsule import (
    P3CurrentCapsule,
    build_p3_current_capsule,
)
from pitchlog.sync.past_correction_paged import (
    P3PagedPreparationProof,
    PastCorrectionPageUnavailable,
    visit_p3_lineup_correction_pages,
)
from pitchlog.sync.past_correction_preparation import (
    PastCorrectionContentRejected,
    PreparedP3LineupCorrection,
    prepare_p3_lineup_correction,
)
from pitchlog.sync.past_correction_stats import (
    P3StatsCandidate,
    PastCorrectionStatsUnsupported,
    evaluate_p3_capsule_stats,
)
from pitchlog.sync.ports import PortWriter
from pitchlog.sync.source_binding import _E1CoreSource


class PastCorrectionExecutionError(RuntimeError):
    """P3の同一実行資格または準備済み全値が不成立。"""


@dataclass(slots=True, repr=False)
class _Execution:
    """実取引内だけのP3訂正frame。"""

    handle: transaction._TenantTransaction
    writer: PortWriter
    source: _E1CoreSource
    event: SyncEvent
    lifetime: tuple[object, object]
    runtime: object
    capsule_id: UUID
    change_event_id: UUID
    preparation: PreparedP3LineupCorrection | None = None
    sealed_preparation: PreparedP3LineupCorrection | None = None
    checkpoint: LineupPrefixDocument | None = None
    sealed_checkpoint: LineupPrefixDocument | None = None
    capsule: P3CurrentCapsule | None = None
    sealed_capsule: P3CurrentCapsule | None = None
    stats: P3StatsCandidate | None = None
    sealed_stats: P3StatsCandidate | None = None
    paged_proof: P3PagedPreparationProof | None = None
    sealed_paged_proof: P3PagedPreparationProof | None = None
    persist_token: object = None
    persist_used: bool = False
    paged_command_index: int = 0
    rejected: bool = False


_EXECUTIONS: dict[object, _Execution] = {}


def _live(
    state: _Execution, *, content: bool = False, projection: bool = False
) -> None:
    """実writer・E1・内容phaseと準備済み全値を毎回照合する。"""
    handle = state.handle
    if (
        type(handle) is not transaction._TenantTransaction
        or _EXECUTIONS.get(handle._state_key) is not state
        or transaction._TRANSACTION_RUNTIMES.get(handle._state_key) is not state.runtime
        or transaction._SYNC_APPLY_ACTIVE.get() is not True
        or type(state.writer) is not PortWriter
        or state.writer._active is not True
        or getattr(state.writer._execute, "__self__", None) is not handle
        or getattr(state.writer._execute, "__func__", None)
        is not transaction._TenantTransaction.run
        or type(state.source) is not _E1CoreSource
        or state.source.scope is not handle
        or state.source.event is not state.event
        or (state.source.write_started and not projection)
        or (projection and not state.source.write_started)
        or (state.preparation is None and state.paged_proof is None)
        != state.rejected
        or (
            state.rejected
            and (
                state.checkpoint is not None
                or state.capsule is not None
                or state.stats is not None
                or state.paged_proof is not None
            )
        )
        or (
            state.paged_proof is not None
            and (
                type(state.paged_proof) is not P3PagedPreparationProof
                or state.sealed_paged_proof != state.paged_proof
                or state.paged_proof.watermark <= 25
                or state.preparation is not None
                or state.capsule is not None
                or state.stats is not None
                or state.checkpoint != state.paged_proof.next_checkpoint
                or state.sealed_checkpoint != state.checkpoint
            )
        )
        or (
            state.preparation is not None
            and (
                state.sealed_preparation is None
                or state.preparation != state.sealed_preparation
                or type(state.checkpoint) is not LineupPrefixDocument
                or state.sealed_checkpoint != state.checkpoint
                or type(state.capsule) is not P3CurrentCapsule
                or state.sealed_capsule != state.capsule
                or state.capsule.next_checkpoint != state.checkpoint
                or type(state.stats) is not P3StatsCandidate
                or state.sealed_stats != state.stats
                or state.stats.capsule_id != state.capsule_id
                or state.preparation.capsule_id != state.capsule_id
                or state.preparation.change_event_id != state.change_event_id
            )
        )
    ):
        raise PastCorrectionExecutionError("P3実行frameが不一致")
    handle._assert_writer_lifetime(state.lifetime)
    state.source.read(handle, state.event)
    handle._assert_writer_lifetime(state.lifetime)
    if content:
        phase = transaction._port_phase(handle)
        if (
            phase is None
            or phase.kind != "content"
            or phase.handle is not handle
            or phase.bound is not state.source.bound
            or phase.snapshot != state.source.bound._phase_snapshot
        ):
            raise PastCorrectionExecutionError("P3内容phaseが不一致")


@contextmanager
def bind_p3_execution(
    handle: transaction._TenantTransaction,
    writer: PortWriter,
    event: SyncEvent,
    source: _E1CoreSource,
):
    """D5・現権利の確認後だけ真正v3原本から有限訂正を準備する。"""
    if (
        type(handle) is not transaction._TenantTransaction
        or type(writer) is not PortWriter
        or type(event) is not SyncEvent
        or type(source) is not _E1CoreSource
        or source.scope is not handle
        or source.event is not event
        or source.write_started
        or handle._state_key in _EXECUTIONS
        or transaction._port_phase(handle) is not None
    ):
        raise PastCorrectionExecutionError("P3実行入口が不一致")
    state = _Execution(
        handle,
        writer,
        source,
        event,
        handle._writer_lifetime(),
        transaction._TRANSACTION_RUNTIMES.get(handle._state_key),
        uuid4(),
        uuid4(),
    )
    key = handle._state_key
    _EXECUTIONS[key] = state
    try:
        # 準備中は未評価のため、同writer/sourceだけを先に照合する。
        handle._assert_writer_lifetime(state.lifetime)
        source.read(handle, event)
        generation, watermark = read_past_correction_watermark(
            handle, UUID(event.game_id)
        )
        if watermark > 25:
            try:
                paged = visit_p3_lineup_correction_pages(
                    handle,
                    event,
                    capsule_id=state.capsule_id,
                    change_event_id=state.change_event_id,
                    bound_source=source,
                    consume=lambda _page: None,
                )
            except PastCorrectionPageUnavailable:
                state.rejected = True
            else:
                if (
                    paged.internal_generation != generation
                    or paged.watermark != watermark
                ):
                    raise PastCorrectionExecutionError("P3頁と資格水位が不一致")
                state.paged_proof = paged
                state.sealed_paged_proof = deepcopy(paged)
                state.checkpoint = paged.next_checkpoint
                state.sealed_checkpoint = deepcopy(paged.next_checkpoint)
        else:
            try:
                prepared = prepare_p3_lineup_correction(
                    handle,
                    event,
                    capsule_id=state.capsule_id,
                    change_event_id=state.change_event_id,
                    bound_source=source,
                )
            except PastCorrectionContentRejected:
                state.rejected = True
            else:
                if (
                    prepared.target_generation != generation
                    or len(prepared.originals) != watermark
                ):
                    raise PastCorrectionExecutionError("P3旧経路と資格水位が不一致")
                capsule = build_p3_current_capsule(prepared)
                try:
                    stats = evaluate_p3_capsule_stats(capsule)
                except PastCorrectionStatsUnsupported:
                    state.rejected = True
                else:
                    state.preparation = prepared
                    state.sealed_preparation = deepcopy(prepared)
                    state.capsule = capsule
                    state.sealed_capsule = deepcopy(capsule)
                    state.stats = stats
                    state.sealed_stats = deepcopy(stats)
                    state.checkpoint = capsule.next_checkpoint
                    state.sealed_checkpoint = deepcopy(state.checkpoint)
        _live(state)
        yield
    finally:
        if _EXECUTIONS.get(key) is state:
            del _EXECUTIONS[key]
        state.preparation = None
        state.sealed_preparation = None
        state.checkpoint = None
        state.sealed_checkpoint = None
        state.capsule = None
        state.sealed_capsule = None
        state.stats = None
        state.sealed_stats = None
        state.paged_proof = None
        state.sealed_paged_proof = None


def p3_content_result(
    handle: transaction._TenantTransaction, event: SyncEvent, writer: PortWriter
) -> bool:
    """自由boolを受け取らず実sourceの準備結果だけをcontent phaseで読む。"""
    state = _EXECUTIONS.get(handle._state_key)
    if (
        type(state) is not _Execution
        or state.event is not event
        or state.writer is not writer
    ):
        raise PastCorrectionExecutionError("P3内容参照が不一致")
    _live(state, content=True)
    return not state.rejected


def p3_change_event_id(
    handle: transaction._TenantTransaction, event: SyncEvent, writer: PortWriter
) -> UUID:
    """T2前の実frameが確保したevent IDだけを返す。"""
    state = _EXECUTIONS.get(handle._state_key)
    if (
        type(state) is not _Execution
        or state.event is not event
        or state.writer is not writer
        or state.rejected
    ):
        raise PastCorrectionExecutionError("P3 T2元参照が不一致")
    _live(state)
    return state.change_event_id


def p3_projection_candidate(
    handle: transaction._TenantTransaction, event: SyncEvent, writer: PortWriter
) -> tuple[P3CurrentCapsule, P3StatsCandidate, _E1CoreSource]:
    """T2済み実sourceの全item/新CP/唯一T5評価をT4へ貸す。"""
    state = _EXECUTIONS.get(handle._state_key)
    if (
        type(state) is not _Execution
        or state.event is not event
        or state.writer is not writer
        or state.rejected
        or type(state.capsule) is not P3CurrentCapsule
        or type(state.stats) is not P3StatsCandidate
    ):
        raise PastCorrectionExecutionError("P3 T4元参照が不一致")
    _live(state, projection=True)
    return state.capsule, state.stats, state.source


def p3_paged_projection_candidate(
    handle: transaction._TenantTransaction, event: SyncEvent, writer: PortWriter
) -> tuple[P3PagedPreparationProof, _E1CoreSource] | None:
    """同一実frameの25件超準備sealだけをT4へ貸す。"""
    state = _EXECUTIONS.get(handle._state_key)
    if (
        type(state) is not _Execution
        or state.event is not event
        or state.writer is not writer
        or state.rejected
    ):
        raise PastCorrectionExecutionError("P3 T4頁元参照が不一致")
    _live(state, projection=True)
    if state.paged_proof is None:
        return None
    return state.paged_proof, state.source


def p3_paged_ids(
    handle: transaction._TenantTransaction, event: SyncEvent, writer: PortWriter
) -> tuple[UUID, UUID]:
    """T2前に同実frameが確保したcapsule/change event IDを返す。"""
    state = _EXECUTIONS.get(handle._state_key)
    if (
        type(state) is not _Execution
        or state.event is not event
        or state.writer is not writer
        or state.paged_proof is None
        or state.rejected
    ):
        raise PastCorrectionExecutionError("P3頁元IDの実frameが不一致")
    _live(state, projection=True)
    return state.capsule_id, state.change_event_id


@contextmanager
def bind_p3_persistence(
    handle: transaction._TenantTransaction,
    event: SyncEvent,
    writer: PortWriter,
    token: object,
) -> Iterator[None]:
    """実frameと同leaseの一個の保存命令だけを同TXへ貸す。"""
    from pitchlog.repositories.past_correction_right import _PersistP3ProjectionToken

    state = _EXECUTIONS.get(handle._state_key)
    if (
        type(state) is not _Execution
        or state.event is not event
        or state.writer is not writer
        or state.persist_token is not None
        or state.persist_used
        or type(token) is not _PersistP3ProjectionToken
    ):
        raise PastCorrectionExecutionError("P3保存命令の実frameが不一致")
    _live(state, projection=True)
    lease = state.source.bound._lease
    if (
        token.attempt_id != lease.attempt_id
        or token.phase_id != lease.phase_id
        or token.binding_nonce != lease.nonce
        or token.device_id != lease.device_id
        or token.game_id != UUID(event.game_id)
    ):
        raise PastCorrectionExecutionError("P3保存命令の実leaseが不一致")
    state.persist_token = token
    try:
        yield
        if not state.persist_used:
            raise PastCorrectionExecutionError("P3保存命令が未消費")
    finally:
        state.persist_token = None


@contextmanager
def bind_p3_paged_persistence(
    handle: transaction._TenantTransaction,
    event: SyncEvent,
    writer: PortWriter,
    token: object,
) -> Iterator[None]:
    """頁保存の各固定命令を同実frame/leaseへ一度だけ結ぶ。"""
    from pitchlog.repositories.past_correction_paged_tokens import (
        _AppendP3ProjectionPageToken,
        _BeginP3ProjectionPageToken,
        _FinalizeP3ProjectionPageToken,
    )

    state = _EXECUTIONS.get(handle._state_key)
    if (
        type(state) is not _Execution
        or state.event is not event
        or state.writer is not writer
        or state.paged_proof is None
        or state.persist_token is not None
        or state.persist_used
        or type(token)
        not in {
            _BeginP3ProjectionPageToken,
            _AppendP3ProjectionPageToken,
            _FinalizeP3ProjectionPageToken,
        }
    ):
        raise PastCorrectionExecutionError("P3頁保存命令の実frameが不一致")
    _live(state, projection=True)
    typed_token = cast(
        _BeginP3ProjectionPageToken
        | _AppendP3ProjectionPageToken
        | _FinalizeP3ProjectionPageToken,
        token,
    )
    lease = state.source.bound._lease
    if (
        typed_token.attempt_id != lease.attempt_id
        or typed_token.phase_id != lease.phase_id
        or typed_token.binding_nonce != lease.nonce
        or typed_token.device_id != lease.device_id
        or typed_token.game_id != UUID(event.game_id)
        or (
            isinstance(
                typed_token,
                (_AppendP3ProjectionPageToken, _FinalizeP3ProjectionPageToken),
            )
            and typed_token.capsule_id != state.capsule_id
        )
    ):
        raise PastCorrectionExecutionError("P3頁保存命令の実leaseが不一致")
    prior_index = state.paged_command_index
    state.persist_token = token
    try:
        yield
        if state.paged_command_index != prior_index + 1:
            raise PastCorrectionExecutionError("P3頁保存命令が未消費")
    finally:
        state.persist_token = None


def consume_p3_paged_persistence(
    handle: transaction._TenantTransaction, token: object
) -> None:
    """begin→全頁append→finalizeの順だけを実TXで消費する。"""
    from pitchlog.repositories.past_correction_paged_tokens import (
        _AppendP3ProjectionPageToken,
        _BeginP3ProjectionPageToken,
        _FinalizeP3ProjectionPageToken,
    )

    state = _EXECUTIONS.get(handle._state_key)
    if (
        type(state) is not _Execution
        or state.paged_proof is None
        or state.persist_token is not token
        or state.persist_used
    ):
        raise PastCorrectionExecutionError("P3頁関数に自由tokenを渡せない")
    _live(state, projection=True)
    index = state.paged_command_index
    if not (
        (index == 0 and type(token) is _BeginP3ProjectionPageToken)
        or (
            1 <= index <= state.paged_proof.page_count
            and type(token) is _AppendP3ProjectionPageToken
        )
        or (
            index == state.paged_proof.page_count + 1
            and type(token) is _FinalizeP3ProjectionPageToken
        )
    ):
        raise PastCorrectionExecutionError("P3頁関数の順序が不一致")
    state.paged_command_index += 1
    if type(token) is _FinalizeP3ProjectionPageToken:
        state.persist_used = True


def consume_p3_persistence(
    handle: transaction._TenantTransaction, token: object
) -> None:
    """同scopeの一度だけの関数実行直前にframeを消費する。"""
    state = _EXECUTIONS.get(handle._state_key)
    if (
        type(state) is not _Execution
        or state.persist_token is not token
        or state.persist_used
    ):
        raise PastCorrectionExecutionError("P3保存関数に自由tokenを渡せない")
    _live(state, projection=True)
    state.persist_used = True
