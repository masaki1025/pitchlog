"""真正sourceを既終了再開host一回へ結び、同TXのopaque frameを発行する。"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.domainrt.game_lifecycle import (
    LifecycleProtocolError,
    LifecycleRequest,
    evaluate_game_lifecycle,
)
from pitchlog.domainrt.host import DomainRuntimeError, NodeDomainHost, open_domain_host
from pitchlog.repositories import transaction
from pitchlog.repositories.nonplay_prefix import (
    _live,
    _read_prefix,
    read_confirmed_nonplay_prefix,
)
from pitchlog.sync.first_ball_execution import _same_wire_value
from pitchlog.sync.idempotency import _json_value, event_source
from pitchlog.sync.lifecycle_payload import (
    LifecyclePayloadError,
    read_lifecycle_event,
)
from pitchlog.sync.lifecycle_ports import _LIFECYCLE_CONTENT_REJECTION_REASON
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter
from pitchlog.sync.source_binding import _E1CoreSource
from pitchlog.sync.stage_timing import TimedOpen, stage


class LifecycleExecutionError(RuntimeError):
    """資格・hostの不明を恒久拒否や成功へ補完しない。"""


_LIFECYCLE_EVENT_FIELDS = (
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


class LifecycleFrame:
    """実評価区間だけで発行され、自由constructorは拒否する。"""

    __slots__ = ()

    def __new__(cls):
        """JSON値をframe資格にしない。"""
        raise LifecycleExecutionError("終了再開frameは自由生成できません")


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
    frame: LifecycleFrame | None = None
    frame_id: object = None
    event_id: object = None
    projected: object = None
    projection_call: object = None
    completed_projected: object = None
    receipt_id: object = None
    request: object = None
    lifecycle: object = None
    lifecycle_anchor: object = None


_EXECUTIONS = {}


def _resolve_lifecycle_references(payload, checkpoint, lifecycle, event):
    """保存済み終端と予約値を照合し、真正な計算入力だけを返す。"""
    content = checkpoint["content"]
    ref = payload["checkpointRef"]
    head = content["d1Head"]["source"]
    predecessor = (
        head["gameId"] == event.game_id
        and head["generation"] == event.d4
        and int(head["d1"]) == event.d1 - 1
        and int(content["d3"]) == event.d1 - 1
    )
    if ref["kind"] == "confirmed":
        valid_ref = {k: v for k, v in ref.items() if k != "kind"} == checkpoint["ref"]
    elif ref["kind"] == "queued_predecessor":
        valid_ref = (
            predecessor
            and all(ref[k] == head[v] for k, v in (("d4", "generation"), ("d5", "d5")))
            and ref["d1"] == int(head["d1"])
        )
    else:
        bridges = content.get("controlBridges", [])
        terminal = bridges[-1] if bridges else None
        valid_ref = (
            predecessor
            and terminal is not None
            and terminal["source"] == head
            and {k: ref[k] for k in ("id", "revision", "digest")}
            == terminal["checkpointBefore"]
            and ref["d4"] == head["generation"]
            and ref["d1"] == int(head["d1"])
            and ref["d5"] == head["d5"]
        )
    if not valid_ref:
        raise LifecyclePayloadError("先行prefixの実受理終端が不一致です")
    target = payload["target"]
    if payload["action"] == "end":
        return None
    if target["kind"] == "confirmed":
        resolved = {k: v for k, v in target.items() if k != "kind"}
    else:
        bridges = content.get("controlBridges", [])
        last_end = next((b for b in reversed(bridges) if b["action"] == "end"), None)
        if (
            last_end is None
            or last_end["source"]["gameId"] != event.game_id
            or last_end["source"]["generation"] != target["d4"]
            or int(last_end["source"]["d1"]) != target["d1"]
            or last_end["source"]["d5"] != target["d5"]
            or last_end["source"]["eventId"] != target["eventId"]
            or last_end["kernel"]["request"]["event"]["receiptId"]
            != target["receiptId"]
        ):
            raise LifecyclePayloadError("先行終了の実受理結果が不一致です")
        resolved = {
            "version": last_end["kernel"]["response"]["value"]["lifecycle"]["active"][
                "version"
            ],
            "eventId": target["eventId"],
            "receiptId": target["receiptId"],
        }
    if resolved != lifecycle["active"]:
        raise LifecyclePayloadError("追記再開の現行終了版が不一致です")
    return resolved


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
        raise LifecycleExecutionError("終了再開の同writer実参照が不一致です")
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
            raise LifecycleExecutionError("終了再開評価済み全値が変更されました")
    if state.lifecycle_anchor is not None:
        request, request_raw, receipt = state.lifecycle_anchor
        if (
            state.request is not request
            or request.json != request_raw
            or state.receipt_id != receipt
        ):
            raise LifecycleExecutionError("終了再開の評価入力/receiptが改変されました")
    if content:
        phase = transaction._port_phase(handle)
        if (
            phase is None
            or phase.kind != "content"
            or phase.handle is not handle
            or phase.bound is not state.source.bound
            or phase.snapshot != state.source.bound._phase_snapshot
        ):
            raise LifecycleExecutionError("終了再開content phaseが不一致です")
        handle._assert_writer_lifetime(state.lifetime)
        state.source.read(handle, state.event)
        handle._assert_writer_lifetime(state.lifetime)
    else:
        _live(handle, state.source, state.event, state.lifetime, state.runtime)


@contextmanager
def _bind_lifecycle_execution(handle, writer, event, source):
    """核D5/権利/順序後の内容段でsourceとhostを一回だけ読む。"""
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
        raise LifecycleExecutionError("終了再開の発行入口が不一致です")
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
                payload = read_lifecycle_event(event).to_wire()
                selected = source.read(handle, event)
                if selected.origin != "e1" or selected.wire_event is None:
                    raise LifecycleExecutionError("終了再開は真正E1だけを使用します")
                original = _json_value(selected.wire_event.wire_event)
                if _canonical_json(original) != _canonical_json(
                    _json_value(event_source(event))
                ):
                    raise LifecyclePayloadError("終了再開原wireとDTOの全値が不一致です")
            except LifecyclePayloadError:
                state.phase = "rejected"
            else:
                host = stack.enter_context(TimedOpen(open_domain_host))
                if type(host) is not NodeDomainHost:
                    raise LifecycleExecutionError("終了再開の実hostが不一致です")
                digest = host.artifact_sha256
                prefix = stack.enter_context(
                    read_confirmed_nonplay_prefix(
                        handle, event, source, artifact_sha256=digest
                    )
                )
                value, _ = _read_prefix(prefix, handle, source, event)
                cp = value["checkpoint"]
                from pitchlog.repositories.game_lifecycle import _read_lifecycle_state

                state.lifecycle = _read_lifecycle_state(handle, source, event)
                try:
                    resolved_target = _resolve_lifecycle_references(
                        payload, cp, state.lifecycle, event
                    )
                except LifecyclePayloadError:
                    state.phase = "rejected"
                else:
                    state.frame_id = uuid4()
                    state.event_id = UUID(payload["event"]["eventId"])
                    state.receipt_id = UUID(payload["event"]["receiptId"])
                    request = LifecycleRequest(
                        _canonical_json(
                            {
                                "formatVersion": "native-game-lifecycle-v1",
                                "action": payload["action"],
                                "current": cp["content"]["restored"]["current"],
                                "lifecycle": state.lifecycle,
                                "target": resolved_target,
                                "event": {
                                    "eventId": str(state.event_id),
                                    "receiptId": str(state.receipt_id),
                                },
                            }
                        )
                    )
                    _execution_live(state)
                    with stage("host_call"):
                        response = evaluate_game_lifecycle(host, request)
                    _execution_live(state)
                    result = response.to_wire()
                    if not result["ok"]:
                        state.phase = "rejected"
                    else:
                        state.prefix, state.payload, state.response, state.request = (
                            prefix,
                            payload,
                            response,
                            request,
                        )
                        state.artifact = digest
                        state.frame = object.__new__(LifecycleFrame)
                        state.anchor = (
                            (state.payload, _canonical_json(state.payload)),
                            (state.response, state.response.json),
                            state.artifact,
                            state.prefix,
                            state.frame,
                            state.frame_id,
                            state.event_id,
                        )
                        state.lifecycle_anchor = (
                            request,
                            request.json,
                            state.receipt_id,
                        )
                        state.phase = "ready"
            _execution_live(state)
            yield
    except (DomainRuntimeError, LifecycleProtocolError) as error:
        raise LifecycleExecutionError("終了再開の真正host/応答が不成立です") from error
    finally:
        if _EXECUTIONS.get(key) is state:
            del _EXECUTIONS[key]
        state.phase = "closed"
        state.completed_projected = state.lifecycle = state.request = None
        state.frame = state.prefix = state.payload = state.response = None


def _lifecycle_content_result(handle, event, writer) -> tuple[bool, str | None]:
    """既核のcontent phaseから真正評価状態だけを読む。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None:
        raise LifecycleExecutionError("終了再開評価が未発行です")
    _execution_live(state, content=True)
    if (
        event is not state.event
        or writer is not state.writer
        or state.source.write_started
        or state.phase not in {"ready", "rejected"}
    ):
        raise LifecycleExecutionError("終了再開内容の実参照が不一致です")
    if state.phase == "ready":
        return True, None
    return False, _LIFECYCLE_CONTENT_REJECTION_REASON


def _reserved_lifecycle_event_id(handle, event):
    """核の元INSERTへ同評価の予約idだけを渡す。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None:
        raise LifecycleExecutionError("終了再開評価が未発行です")
    _execution_live(state)
    if (
        state.phase != "ready"
        or type(event) is not SyncEvent
        or any(
            not _same_wire_value(getattr(state.event, name), getattr(event, name))
            for name in _LIFECYCLE_EVENT_FIELDS
        )
    ):
        raise LifecycleExecutionError("終了再開の予約原本idが不一致です")
    return state.event_id


@contextmanager
def _bind_lifecycle_projection(handle, writer, event, projected):
    """T1/T2/T3後の同核呼出区間だけへframeを貸与する。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None:
        raise LifecycleExecutionError("終了再開評価が未発行です")
    _execution_live(state)
    if (
        state.phase != "ready"
        or state.writer is not writer
        or state.event is not event
        or type(projected) is not SyncEvent
        or not state.source.write_started
        or any(
            not _same_wire_value(getattr(event, name), getattr(projected, name))
            for name in _LIFECYCLE_EVENT_FIELDS
        )
    ):
        raise LifecycleExecutionError("終了再開投影の元要求が不一致です")
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


def _consume_lifecycle_frame(handle, event, writer):
    """sameSession/source/一回frameを消費し固定投影だけへ渡す。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None:
        raise LifecycleExecutionError("終了再開評価が未発行です")
    _execution_live(state)
    if (
        state.phase != "projecting"
        or state.projected is not event
        or state.writer is not writer
        or type(state.frame) is not LifecycleFrame
        or state.projection_call is None
        or state.frame_id is None
    ):
        raise LifecycleExecutionError("終了再開frameが未発行又は消費済みです")
    state.frame = None
    state.phase = "consumed"
    return state


def _require_lifecycle_projection_completed(handle, event):
    """実consume成功以外を完了にしない。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None:
        raise LifecycleExecutionError("終了再開評価が未発行です")
    _execution_live(state)
    if state.event is not event or state.phase != "projected":
        raise LifecycleExecutionError("終了再開の実DB完了がありません")


_QUALIFICATIONS = {}


@contextmanager
def _lifecycle_qualification_scope(handle, source):
    """D5後の真正sourceだけを実device/right関数選択へ貸与する。"""
    if (
        type(handle) is not transaction._TenantTransaction
        or type(source) is not _E1CoreSource
        or source.scope is not handle
        or source.write_started
        or handle._state_key in _QUALIFICATIONS
        or source.event.v5 not in {"game_end_declaration", "game_reopen"}
    ):
        raise LifecycleExecutionError("終了再開の実rights資格が不一致です")
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


def _lifecycle_qualification_active(handle):
    """Caller boolではなく寿命に登録済みの実sourceを核だけが検査する。"""
    if type(handle) is not transaction._TenantTransaction:
        raise LifecycleExecutionError("終了再開の実handleが必要です")
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
            raise LifecycleExecutionError("終了再開rightsの同scopeが不一致です")
        handle._assert_writer_lifetime(lifetime)
        source.read(handle, source.event)
        handle._assert_writer_lifetime(lifetime)
    return True


def _lifecycle_native_ledger_state(handle, event, writer):
    """7Aのstored分類後にだけfresh実frameを再検査する核用hook。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None:
        raise LifecycleExecutionError("終了再開native frameが未発行です")
    _execution_live(state)
    if (
        state.event is not event
        or state.writer is not writer
        or state.phase != "ready"
        or type(state.frame) is not LifecycleFrame
        or not state.source.write_started
    ):
        raise LifecycleExecutionError("終了再開native台帳の実frameが不一致です")
    return state
