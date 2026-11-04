"""通常投球の実source/同writer/prefix/一回評価へ束縛する私有frame。"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

from pitchlog.domainrt.first_pitch import FirstPitchRequest
from pitchlog.domainrt.host import NodeDomainHost, open_domain_host
from pitchlog.domainrt.ordinary_pitch_continuation import (
    OrdinaryContinuationFailure,
    OrdinaryContinuationRequest,
    OrdinaryContinuationSuccess,
    decode_ordinary_continuation_response,
)
from pitchlog.repositories import transaction
from pitchlog.repositories.ordinary_prefix import read_confirmed_ordinary_prefix
from pitchlog.sync.first_ball_execution import _same_wire_value
from pitchlog.sync.idempotency import _json_value
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ordering import _MAX_D2
from pitchlog.sync.ordinary_pitch_payload import (
    OrdinaryPitchCalculation,
    OrdinaryPitchPayloadError,
    OrdinaryPitchPlayPayload,
    read_ordinary_pitch_payload,
    select_ordinary_pitch_participants,
)
from pitchlog.sync.ports import PortWriter
from pitchlog.sync.source_binding import _E1CoreSource


class OrdinaryPitchExecutionError(RuntimeError):
    """資格/実評価の不成立を恒久内容拒否へ混ぜない。"""

    def __init__(self):
        """原値/秘密を含めない。"""
        super().__init__("通常投球の実prefix/frameを確認できません")


class OrdinaryPitchFrame:
    """自由生成もrecordからの発行も許さない私有参照。"""

    __slots__ = ()

    def __new__(cls):
        """実source評価の内部だけが発行する。"""
        raise OrdinaryPitchExecutionError


@dataclass(slots=True, repr=False)
class _Execution:
    handle: object
    writer: PortWriter
    source: _E1CoreSource
    event: SyncEvent
    lifetime: tuple[object, object]
    runtime: object
    frame: OrdinaryPitchFrame | None = None
    frame_id: UUID | None = None
    prefix: object = None
    payload: OrdinaryPitchPlayPayload | None = None
    phase: str = "preparing"
    projected: SyncEvent | None = None
    projection_call: object = None
    preparation_token: object = None
    preparation_digest: str | None = None
    preparation_used: bool = False


_EXECUTIONS: dict[object, _Execution] = {}


def _live(state):
    """単一の実source/lease検査へ委譲し、writer/runtimeの置換も拒否する。"""
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
    ):
        raise OrdinaryPitchExecutionError
    handle._assert_writer_lifetime(state.lifetime)
    state.source.read(handle, state.event)
    handle._assert_writer_lifetime(state.lifetime)


@contextmanager
def _bind_ordinary_pitch_execution(handle, writer, event, source):
    """D5/順序/実権利後の実内容段でだけ独立frameを評価する。"""
    if (
        type(handle) is not transaction._TenantTransaction
        or type(writer) is not PortWriter
        or type(event) is not SyncEvent
        or type(source) is not _E1CoreSource
        or handle._state_key in _EXECUTIONS
        or transaction._port_phase(handle) is not None
        or source.write_started
    ):
        raise OrdinaryPitchExecutionError
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
        _live(state)
        try:
            raw_v7 = json.dumps(
                _json_value(event.v7), ensure_ascii=False, allow_nan=False
            )
            raw_v8 = json.dumps(
                _json_value(event.v8), ensure_ascii=False, allow_nan=False
            )
            supplied = OrdinaryPitchPlayPayload.model_validate_json(raw_v7)
        except (TypeError, ValueError, RecursionError):
            state.phase = "rejected"
        if state.phase != "rejected":
            with open_domain_host() as host:
                if type(host) is not NodeDomainHost or type(host._source) is not str:
                    raise OrdinaryPitchExecutionError
                artifact_sha256 = hashlib.sha256(host._source.encode()).hexdigest()
                prefix = read_confirmed_ordinary_prefix(
                    handle, event, source, artifact_sha256=artifact_sha256
                )
                _live(state)
                doc = prefix.checkpoint
                requested = supplied.calculation.request.t1
                request = _request_from_checkpoint(doc, requested)
                response = decode_ordinary_continuation_response(
                    host.call(
                        "deriveOrdinaryPitchWithContinuation",
                        request.model_dump_json(by_alias=True, exclude_unset=True),
                    )
                )
                _live(state)
                if isinstance(response, OrdinaryContinuationFailure):
                    if response.error.code in {
                        "UNSUPPORTED_T1_SCOPE",
                        "UNSUPPORTED_T2_SCOPE",
                    }:
                        from pitchlog.sync.apply import _E1OutOfScope

                        raise _E1OutOfScope("通常37の未対応操作")
                    raise OrdinaryPitchExecutionError
                if type(response) is not OrdinaryContinuationSuccess:
                    raise OrdinaryPitchExecutionError
                calculation = OrdinaryPitchCalculation(
                    formatVersion="ordinary-pitch-calculation-v1",
                    artifactSha256=artifact_sha256,
                    request=request,
                    response=response,
                )
                people = select_ordinary_pitch_participants(prefix.roster, doc.after)
                try:
                    state.payload = read_ordinary_pitch_payload(
                        raw_v7,
                        raw_v8,
                        expected_calculation=calculation,
                        expected_participants=people,
                    )
                except OrdinaryPitchPayloadError:
                    state.phase = "rejected"
                else:
                    state.prefix = prefix
                    state.frame = object.__new__(OrdinaryPitchFrame)
                    state.frame_id = uuid4()
                    state.phase = "ready"
        _live(state)
        yield
    finally:
        if _EXECUTIONS.get(key) is state:
            del _EXECUTIONS[key]
        state.phase = "closed"
        state.frame = None
        state.prefix = None
        state.payload = None


def _ordinary_content_result(handle, event, writer):
    """実frame状態をcontent phaseで確認し、自由boolを受け取らない。"""
    if type(handle) is not transaction._TenantTransaction:
        raise OrdinaryPitchExecutionError
    state = _EXECUTIONS.get(handle._state_key)
    if type(state) is not _Execution:
        raise OrdinaryPitchExecutionError
    _live(state)
    phase = transaction._port_phase(handle)
    if (
        phase is None
        or phase.kind != "content"
        or phase.handle is not handle
        or phase.bound is not state.source.bound
        or phase.snapshot != state.source.bound._phase_snapshot
        or event is not state.event
        or writer is not state.writer
        or state.source.write_started
        or state.phase not in {"ready", "rejected"}
        or (state.phase == "ready" and type(state.frame) is not OrdinaryPitchFrame)
    ):
        raise OrdinaryPitchExecutionError
    return state.phase == "ready"


@contextmanager
def _bind_ordinary_pitch_projection(handle, writer, event, projected):
    """実核の採番済みprojection呼出区間だけでframeを貸与する。"""
    if type(handle) is not transaction._TenantTransaction:
        raise OrdinaryPitchExecutionError
    state = _EXECUTIONS.get(handle._state_key)
    if type(state) is not _Execution:
        raise OrdinaryPitchExecutionError
    _live(state)
    if (
        state.phase != "ready"
        or writer is not state.writer
        or event is not state.event
        or type(projected) is not SyncEvent
        or projected is event
        or transaction._port_phase(handle) is not None
        or not state.source.write_started
        or type(projected.v6) is not int
        or not 0 <= projected.v6 <= _MAX_D2
        or any(
            not _same_wire_value(getattr(event, name), getattr(projected, name))
            for name in (
                "d5",
                "game_id",
                "d1",
                "d4",
                "v5",
                "v7",
                "v8",
                "v9",
                "v10",
                "v11",
            )
        )
    ):
        raise OrdinaryPitchExecutionError
    state.projected = projected
    state.projection_call = object()
    state.phase = "projecting"
    try:
        yield
        _live(state)
    finally:
        state.projected = None
        state.projection_call = None
        if state.phase == "projecting":
            state.phase = "closed"


def _consume_ordinary_pitch_frame(handle, projected, writer):
    """同呼出区間の真正frameだけを一回消費し、DB保存は別に要求する。"""
    if type(handle) is not transaction._TenantTransaction:
        raise OrdinaryPitchExecutionError
    state = _EXECUTIONS.get(handle._state_key)
    if type(state) is not _Execution:
        raise OrdinaryPitchExecutionError
    _live(state)
    if (
        state.phase != "projecting"
        or state.projected is not projected
        or state.writer is not writer
        or state.projection_call is None
        or state.frame_id is None
        or type(state.frame) is not OrdinaryPitchFrame
        or state.payload is None
        or state.prefix is None
        or transaction._port_phase(handle) is not None
    ):
        raise OrdinaryPitchExecutionError
    state.phase = "consumed"
    state.frame = None
    return state


def _require_ordinary_projection_completed(handle, event):
    """実INSERT/checkpoint完了がないPortを成功扱いしない。"""
    if type(handle) is not transaction._TenantTransaction:
        raise OrdinaryPitchExecutionError
    state = _EXECUTIONS.get(handle._state_key)
    if type(state) is not _Execution:
        raise OrdinaryPitchExecutionError
    _live(state)
    if state.event is not event or state.phase != "projected":
        raise OrdinaryPitchExecutionError


_QUALIFICATIONS: dict[object, _E1CoreSource] = {}
_QUALIFIED_EPOCHS: dict[object, tuple[_E1CoreSource, int]] = {}


@contextmanager
def _ordinary_qualification_scope(handle, source):
    """実受付のordinary元eventだけをdevice/right関数選択へ束縛する。"""
    from collections.abc import Mapping

    if (
        type(handle) is not transaction._TenantTransaction
        or type(source) is not _E1CoreSource
        or source.scope is not handle
        or source.write_started
        or handle._state_key in _QUALIFICATIONS
        or transaction._port_phase(handle) is not None
        or not isinstance(source.event.v7, Mapping)
        or source.event.v7.get("formatVersion") != "ordinary-pitch-play-v1"
    ):
        raise OrdinaryPitchExecutionError
    source.read(handle, source.event)
    lifetime = handle._writer_lifetime()
    key = handle._state_key
    _QUALIFICATIONS[key] = source
    try:
        yield
        handle._assert_writer_lifetime(lifetime)
    finally:
        if _QUALIFICATIONS.get(key) is source:
            del _QUALIFICATIONS[key]
        _QUALIFIED_EPOCHS.pop(key, None)


def _ordinary_qualification_active(handle):
    """自由boolではなく実source/leaseから関数選択を核だけが確認する。"""
    source = _QUALIFICATIONS.get(handle._state_key)
    if source is None:
        return False
    if type(source) is not _E1CoreSource or source.scope is not handle:
        raise OrdinaryPitchExecutionError
    source.read(handle, source.event)
    return True


@contextmanager
def _bind_ordinary_preparation(state, token):
    """実frame消費後の同scopeで生成したprepare一個だけをSQL入口へ貸す。"""
    from pitchlog.repositories.ordinary_pitch_qualification import (
        PrepareOrdinaryProjectionToken,
    )
    from pitchlog.sync.idempotency import source_fingerprint

    _live(state)
    if (
        state.phase != "consumed"
        or state.projection_call is None
        or state.preparation_token is not None
        or state.preparation_used
        or type(token) is not PrepareOrdinaryProjectionToken
    ):
        raise OrdinaryPitchExecutionError
    lease = state.source.bound._lease
    if (
        token.attempt_id != lease.attempt_id
        or token.phase_id != lease.phase_id
        or token.binding_nonce != lease.nonce
        or token.device_id != lease.device_id
        or token.game_id != UUID(state.event.game_id)
    ):
        raise OrdinaryPitchExecutionError
    state.preparation_token = token
    state.preparation_digest = source_fingerprint(
        {
            "preparation_json": token.preparation_json,
            "attempt_id": str(token.attempt_id),
            "phase_id": str(token.phase_id),
            "device_id": str(token.device_id),
            "game_id": str(token.game_id),
            "binding_nonce": token.binding_nonce.hex(),
        }
    )
    try:
        yield
        _live(state)
        if not state.preparation_used:
            raise OrdinaryPitchExecutionError
    finally:
        state.preparation_token = None
        state.preparation_digest = None


def _consume_ordinary_preparation(handle, token):
    """実行器がSQLより先にobjectidentity/全値digest/生存scopeを一回照合する。"""
    from pitchlog.sync.idempotency import source_fingerprint

    if type(handle) is not transaction._TenantTransaction:
        raise OrdinaryPitchExecutionError
    state = _EXECUTIONS.get(handle._state_key)
    if type(state) is not _Execution:
        raise OrdinaryPitchExecutionError
    _live(state)
    if (
        state.phase != "consumed"
        or state.projection_call is None
        or state.preparation_token is not token
        or state.preparation_used
    ):
        raise OrdinaryPitchExecutionError
    digest = source_fingerprint(
        {
            "preparation_json": token.preparation_json,
            "attempt_id": str(token.attempt_id),
            "phase_id": str(token.phase_id),
            "device_id": str(token.device_id),
            "game_id": str(token.game_id),
            "binding_nonce": token.binding_nonce.hex(),
        }
    )
    if state.preparation_digest != digest:
        raise OrdinaryPitchExecutionError
    state.preparation_used = True


def _record_ordinary_right_epoch(handle, phase, epoch):
    """実rights phaseのRG1検証済epochだけを当該source寿命へ保持する。"""
    source = _QUALIFICATIONS.get(handle._state_key)
    if (
        type(source) is not _E1CoreSource
        or transaction._port_phase(handle) is not phase
        or phase.kind != "rights"
        or phase.bound is not source.bound
        or type(epoch) is not int
        or not 0 < epoch < 2**63
        or transaction._verified_recovery_epoch(handle, phase) != epoch
    ):
        raise OrdinaryPitchExecutionError
    source.read(handle, source.event)
    _QUALIFIED_EPOCHS[handle._state_key] = (source, epoch)


def _ordinary_verified_epoch(handle, source):
    """同source/同scopeの実rights確認値を計算段へ渡す。"""
    captured = _QUALIFIED_EPOCHS.get(handle._state_key)
    if (
        captured is None
        or captured[0] is not source
        or _QUALIFICATIONS.get(handle._state_key) is not source
    ):
        raise OrdinaryPitchExecutionError
    source.read(handle, source.event)
    return captured[1]


def _request_from_checkpoint(doc, requested):
    """確認済み原本のmodelを保ち、Python境界でtupleをJSON配列へ変換しない。"""
    return OrdinaryContinuationRequest.model_validate(
        {
            "version": "1",
            "prefixRef": doc.prefix_ref,
            "rules": doc.rules,
            "t1": FirstPitchRequest(
                eventKind=requested.event_kind,
                resultId=requested.result_id,
                pitchEventKind=requested.pitch_event_kind,
                before=doc.after,
            ),
            "prior": {
                "kind": "started-initial" if doc.t2 is None else "evaluated-prefix",
                "prefixRef": doc.prefix_ref,
                "rules": doc.rules,
                "after": doc.after,
                "t2": doc.t2,
            },
        }
    )
