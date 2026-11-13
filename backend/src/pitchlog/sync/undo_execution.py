"""真正sourceを既取消host一回へ結び、同TXのopaque frameを発行する。"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID, uuid4

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.domainrt.host import NodeDomainHost, open_domain_host
from pitchlog.domainrt.undo import UndoRequest, decode_undo_response
from pitchlog.repositories import transaction
from pitchlog.repositories.nonplay_prefix import (
    _live,
    _read_prefix,
    read_confirmed_nonplay_prefix,
)
from pitchlog.sync.first_ball_execution import _same_wire_value
from pitchlog.sync.idempotency import _json_value, event_source
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter
from pitchlog.sync.source_binding import _E1CoreSource
from pitchlog.sync.undo_payload import (
    UndoPayloadError,
    _validate_value,
    read_undo_event,
)
from pitchlog.sync.undo_ports import _UNDO_CONTENT_REJECTION_REASON


class UndoExecutionError(RuntimeError):
    """資格・hostの不明を恒久拒否や成功へ補完しない。"""


class UndoFrame:
    """実評価区間だけで発行され、自由constructorは拒否する。"""

    __slots__ = ()

    def __new__(cls):
        """JSON値をframe資格にしない。"""
        raise UndoExecutionError("取消frameは自由生成できません")


@dataclass(slots=True, repr=False)
class _Execution:
    handle: Any
    writer: PortWriter
    source: _E1CoreSource
    event: SyncEvent
    lifetime: tuple
    runtime: object
    phase: str = "preparing"
    anchor: Any = None
    prefix: Any = None
    payload: Any = None
    response: Any = None
    artifact: str | None = None
    frame: UndoFrame | None = None
    frame_id: object = None
    event_id: object = None
    projected: object = None
    projection_call: object = None
    completed_projected: object = None
    stats_receipt: object = None
    stats_flushed: bool = False


_EXECUTIONS = {}


def _execution_live(state, *, content=False):
    """既writer lease/同scopeと実E1 bindingを現在形で確認する。"""
    handle = state.handle
    if (
        type(handle) is not transaction._TenantTransaction
        or _EXECUTIONS.get(handle._state_key) is not state
        or type(state.writer) is not PortWriter
        or state.writer._active is not True
        or getattr(state.writer._execute, "__self__", None) is not handle
        or getattr(state.writer._execute, "__func__", None)
        is not transaction._TenantTransaction.run
        or transaction._TRANSACTION_RUNTIMES.get(handle._state_key) is not state.runtime
        or transaction._SYNC_APPLY_ACTIVE.get() is not True
    ):
        raise UndoExecutionError("取消の同writer実参照が不一致です")
    if state.anchor is not None:
        payload, response, artifact, prefix, frame, frame_id, event_id = state.anchor
        if (
            state.payload is not payload[0]
            or state.response is not response[0]
            or _canonical_json(state.payload) != payload[1]
            or state.response.json != response[1]
            or state.artifact != artifact
            or state.prefix is not prefix
            or state.frame_id != frame_id
            or state.event_id != event_id
            or (state.phase in {"ready", "projecting"} and state.frame is not frame)
        ):
            raise UndoExecutionError("取消評価済み全値が変更されました")
    if content:
        phase = transaction._port_phase(handle)
        if (
            phase is None
            or phase.kind != "content"
            or phase.handle is not handle
            or phase.bound is not state.source.bound
            or phase.snapshot != state.source.bound._phase_snapshot
        ):
            raise UndoExecutionError("取消content phaseが不一致です")
        handle._assert_writer_lifetime(state.lifetime)
        state.source.read(handle, state.event)
        handle._assert_writer_lifetime(state.lifetime)
    else:
        _live(handle, state.source, state.event, state.lifetime, state.runtime)


@contextmanager
def _bind_undo_execution(
    handle,
    writer,
    event,
    source,
    *,
    validate_target: Callable[[Any], None] | None = None,
):
    """核D5/権利/順序後に保存対象を照合し、同hostを一回評価する。"""
    if (
        type(handle) is not transaction._TenantTransaction
        or type(writer) is not PortWriter
        or type(event) is not SyncEvent
        or type(source) is not _E1CoreSource
        or source.scope is not handle
        or source.event is not event
        or source.write_started
        or handle._state_key in _EXECUTIONS
    ):
        raise UndoExecutionError("取消の発行入口が不一致です")
    state = _Execution(
        handle,
        writer,
        source,
        event,
        handle._writer_lifetime(),
        transaction._TRANSACTION_RUNTIMES.get(handle._state_key),
    )
    key = handle._state_key
    _EXECUTIONS[key] = state
    try:
        with ExitStack() as stack:
            _execution_live(state)
            try:
                payload = read_undo_event(event).to_wire()
                selected = source.read(handle, event)
                if selected.origin != "e1" or selected.wire_event is None:
                    raise UndoExecutionError("取消は真正E1だけを使用します")
                original = _json_value(selected.wire_event.wire_event)
                _validate_value(original, "UndoEvent")
                if _canonical_json(original) != _canonical_json(
                    _json_value(event_source(event))
                ):
                    raise UndoPayloadError("取消原wireとDTOの全値が不一致です")
            except UndoPayloadError:
                state.phase = "rejected"
            else:
                host = stack.enter_context(open_domain_host())
                if type(host) is not NodeDomainHost:
                    raise UndoExecutionError("取消の実hostが不一致です")
                digest = host.artifact_sha256
                prefix = stack.enter_context(
                    read_confirmed_nonplay_prefix(
                        handle, event, source, artifact_sha256=digest
                    )
                )
                value, _, head_position = _read_prefix(
                    prefix, handle, source, event, include_head_position=True
                )
                cp = value["checkpoint"]
                active = value["activeStack"]
                target = event.v10
                if not active:
                    # U4はevent/D1を作らない。既存eventをno-op成功にしない。
                    if validate_target is not None:
                        validate_target(None)
                    state.phase = "rejected"
                else:
                    head = active[0]["play"]["source"]
                    if validate_target is not None:
                        if head_position is None:
                            raise UndoExecutionError("取消対象の保存位置がありません")
                        from pitchlog.sync.prefix_path import P1Target

                        validate_target(
                            P1Target(
                                UUID(head["gameId"]),
                                head_position[0],
                                head_position[1],
                                head["generation"],
                            )
                        )
                    genuine_target = {
                        "game": head["gameId"],
                        "d4": head["generation"],
                        "d1": int(head["d1"]),
                    }
                    if (
                        _canonical_json(payload["expectedCheckpoint"])
                        != _canonical_json(cp["ref"])
                        or not _same_wire_value(target, genuine_target)
                        or payload["artifactSha256"] != digest
                    ):
                        state.phase = "rejected"
                    else:
                        request = UndoRequest(
                            _canonical_json(
                                {
                                    "current": cp["content"]["restored"]["current"],
                                    "history": {
                                        "stack": [
                                            entry["historyEntry"] for entry in active
                                        ]
                                    },
                                }
                            )
                        )
                        _execution_live(state)
                        response = decode_undo_response(
                            host.call("applyUndo", request.json)
                        )
                        _execution_live(state)
                        result = response.to_wire()
                        if not result["ok"]:
                            if result["error"]["code"] == "UNSUPPORTED_T1_SCOPE":
                                from pitchlog.sync.apply import _E1OutOfScope

                                raise _E1OutOfScope("取消の未対応純操作")
                            raise UndoExecutionError("真正取消要求の実評価が不成立です")
                        if result["value"]["operationResult"] != "applied" or result[
                            "value"
                        ]["historyEffect"] != {"pops": "1"}:
                            raise UndoExecutionError("真正取消の一回popが不一致です")
                        if _canonical_json(result["value"]["after"]) != _canonical_json(
                            active[0]["beforeContext"]["current"]
                        ) or _canonical_json(
                            result["value"]["historyContext"]
                        ) != _canonical_json(
                            [entry["historyEntry"] for entry in active[1:]]
                        ):
                            raise UndoExecutionError(
                                "取消の原本前状態/完全tailが不一致です"
                            )
                        actual_calculation = {
                            "request": request.to_wire(),
                            "response": result,
                        }
                        if _canonical_json(payload["calculation"]) != _canonical_json(
                            actual_calculation
                        ):
                            state.phase = "rejected"
                        else:
                            state.prefix, state.payload, state.response = (
                                prefix,
                                payload,
                                response,
                            )
                            state.artifact = digest
                            state.frame = object.__new__(UndoFrame)
                            state.frame_id, state.event_id = uuid4(), uuid4()
                            state.anchor = (
                                (state.payload, _canonical_json(state.payload)),
                                (state.response, state.response.json),
                                state.artifact,
                                state.prefix,
                                state.frame,
                                state.frame_id,
                                state.event_id,
                            )
                            state.phase = "ready"
            _execution_live(state)
            yield
    finally:
        from pitchlog.sync.stats_native_flush import _close_undo_stats_receipt

        _close_undo_stats_receipt(state)
        if _EXECUTIONS.get(key) is state:
            del _EXECUTIONS[key]
        state.phase = "closed"
        state.completed_projected = state.stats_receipt = None
        state.frame = state.prefix = state.payload = state.response = None


def _undo_content_result(handle, event, writer) -> tuple[bool, str | None]:
    """既核のcontent phaseから真正評価状態だけを読む。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None:
        raise UndoExecutionError("取消評価が未発行です")
    _execution_live(state, content=True)
    if (
        event is not state.event
        or writer is not state.writer
        or state.source.write_started
        or state.phase not in {"ready", "rejected"}
    ):
        raise UndoExecutionError("取消内容の実参照が不一致です")
    if state.phase == "ready":
        return True, None
    return False, _UNDO_CONTENT_REJECTION_REASON


def _reserved_undo_event_id(handle, event):
    """核の元INSERTへ同評価の予約idだけを渡す。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None:
        raise UndoExecutionError("取消評価が未発行です")
    _execution_live(state)
    if (
        type(event) is not SyncEvent
        or state.phase != "ready"
        or any(
            not _same_wire_value(getattr(event, name), getattr(state.event, name))
            for name in (
                "d5",
                "game_id",
                "d1",
                "d4",
                "v5",
                "v6",
                "v7",
                "v8",
                "v9",
                "v10",
                "v11",
            )
        )
    ):
        raise UndoExecutionError("取消の予約原本idが不一致です")
    return state.event_id


@contextmanager
def _bind_undo_projection(handle, writer, event, projected):
    """T1/T2/T3後の同核呼出区間だけへframeを貸与する。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None:
        raise UndoExecutionError("取消評価が未発行です")
    _execution_live(state)
    if (
        state.phase != "ready"
        or state.writer is not writer
        or state.event is not event
        or type(projected) is not SyncEvent
        or not state.source.write_started
        or any(
            not _same_wire_value(getattr(event, name), getattr(projected, name))
            for name in (
                "d5",
                "game_id",
                "d1",
                "d4",
                "v5",
                "v6",
                "v7",
                "v8",
                "v9",
                "v10",
                "v11",
            )
        )
    ):
        raise UndoExecutionError("取消投影の元要求が不一致です")
    state.phase = "projecting"
    state.projected, state.projection_call = projected, object()
    try:
        yield
        _execution_live(state)
        if state.phase == "projected":
            state.completed_projected = projected
    finally:
        state.projected = state.projection_call = None
        if state.phase != "projected":
            state.phase = "closed"


def _consume_undo_frame(handle, event, writer):
    """sameSession/source/一回frameを消費し固定投影だけへ渡す。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None:
        raise UndoExecutionError("取消評価が未発行です")
    _execution_live(state)
    if (
        state.phase != "projecting"
        or state.projected is not event
        or state.writer is not writer
        or type(state.frame) is not UndoFrame
        or state.projection_call is None
        or state.frame_id is None
    ):
        raise UndoExecutionError("取消frameが未発行又は消費済みです")
    state.frame = None
    state.phase = "consumed"
    return state


def _require_undo_projection_completed(handle, event):
    """実consume成功以外を完了にしない。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None:
        raise UndoExecutionError("取消評価が未発行です")
    _execution_live(state)
    if state.event is not event or state.phase != "projected":
        raise UndoExecutionError("取消の実DB完了がありません")


_QUALIFICATIONS = {}


@contextmanager
def _undo_qualification_scope(handle, source):
    """D5後の真正sourceだけを実device/right関数選択へ貸与する。"""
    if (
        type(handle) is not transaction._TenantTransaction
        or type(source) is not _E1CoreSource
        or source.scope is not handle
        or source.write_started
        or handle._state_key in _QUALIFICATIONS
        or source.event.v5 not in {"undo", "substitution", "tiebreak_start"}
    ):
        raise UndoExecutionError("取消の実rights資格が不一致です")
    lifetime = handle._writer_lifetime()
    runtime = transaction._TRANSACTION_RUNTIMES.get(handle._state_key)
    _live(handle, source, source.event, lifetime, runtime)
    key = handle._state_key
    _QUALIFICATIONS[key] = (source, lifetime, runtime)
    try:
        yield
        _live(handle, source, source.event, lifetime, runtime)
    finally:
        _QUALIFICATIONS.pop(key, None)


def _undo_qualification_active(handle):
    """Caller boolではなく寿命に登録済みの実sourceを核だけが検査する。"""
    if type(handle) is not transaction._TenantTransaction:
        raise UndoExecutionError("取消の実handleが必要です")
    state = _QUALIFICATIONS.get(handle._state_key)
    if state is None:
        return False
    source, lifetime, runtime = state
    phase = transaction._port_phase(handle)
    if phase is None:
        _live(handle, source, source.event, lifetime, runtime)
    else:
        if (
            phase.kind not in {"device", "rights"}
            or phase.handle is not handle
            or phase.bound is not source.bound
            or phase.snapshot != source.bound._phase_snapshot
            or transaction._TRANSACTION_RUNTIMES.get(handle._state_key) is not runtime
            or transaction._SYNC_APPLY_ACTIVE.get() is not True
            or source.write_started
        ):
            raise UndoExecutionError("取消rightsの同scopeが不一致です")
        handle._assert_writer_lifetime(lifetime)
        source.read(handle, source.event)
        handle._assert_writer_lifetime(lifetime)
    return True


def _undo_native_ledger_state(handle, event, writer):
    """7Aのstored分類後にだけfresh実frameを再検査する核用hook。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None:
        raise UndoExecutionError("取消native frameが未発行です")
    _execution_live(state)
    if (
        state.event is not event
        or state.writer is not writer
        or state.phase != "ready"
        or type(state.frame) is not UndoFrame
        or not state.source.write_started
    ):
        raise UndoExecutionError("取消native台帳の実frameが不一致です")
    return state
