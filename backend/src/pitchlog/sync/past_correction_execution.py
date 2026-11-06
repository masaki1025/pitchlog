"""P3の真正E1 source・同writer・有限v3再評価を同scopeへ閉じる。"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from uuid import UUID, uuid4

from pitchlog.repositories import transaction
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.past_correction_preparation import (
    PastCorrectionContentRejected,
    PreparedP3LineupCorrection,
    prepare_p3_lineup_correction,
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
    rejected: bool = False


_EXECUTIONS: dict[object, _Execution] = {}


def _live(state: _Execution, *, content: bool = False) -> None:
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
        or state.source.write_started
        or (state.preparation is None) != state.rejected
        or (
            state.preparation is not None
            and (
                state.sealed_preparation is None
                or state.preparation != state.sealed_preparation
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
        try:
            prepared = prepare_p3_lineup_correction(
                handle,
                event,
                capsule_id=state.capsule_id,
                change_event_id=state.change_event_id,
            )
        except PastCorrectionContentRejected:
            state.rejected = True
        else:
            state.preparation = prepared
            state.sealed_preparation = deepcopy(prepared)
        _live(state)
        yield
    finally:
        if _EXECUTIONS.get(key) is state:
            del _EXECUTIONS[key]
        state.preparation = None
        state.sealed_preparation = None


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
