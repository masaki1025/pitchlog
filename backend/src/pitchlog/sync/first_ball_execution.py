"""核の⑦だけで実初球評価を保持する。Port/HTTPから資格を発行しない。"""

from __future__ import annotations

import hashlib
import json
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pitchlog.domainrt.first_ball_projection import (
    FirstBallCalculationValue,
    format_first_ball_calculation,
)
from pitchlog.domainrt.first_pitch_continuation import (
    CombinedRequest,
    CombinedSuccess,
    decode_combined_response,
)
from pitchlog.domainrt.host import _product_artifact_paths, _verified_source
from pitchlog.domainrt.initial_game_roster import InitialRosterProjection
from pitchlog.repositories import transaction
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.control_provider.writer_binding import (
    _LIVE_BINDINGS,
    _LiveWriterBinding,
)
from pitchlog.sync.first_ball_bridge import (
    FirstBallContentRejected,
    _bind_e1_first_ball_at_content_stage,
    _read_ready_first_ball_frame,
    evaluate_first_ball_frame,
)
from pitchlog.sync.first_ball_frame import (
    FirstBallBridge,
    FirstBallFrame,
    FirstBallIntent,
)
from pitchlog.sync.first_ball_payload import (
    FirstBallParticipants,
    FirstBallPayloadError,
    FirstBallPayloadValue,
    FirstBallPlayPayload,
    read_first_ball_payload,
)
from pitchlog.sync.idempotency import _json_value
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter
from pitchlog.sync.source_binding import _E1CoreSource
from pitchlog.sync.tokens import PortValidateFirstBallToken

_REASON = "初球の内容が対応範囲又は計算と一致しません"
_INTENT = FirstBallIntent("batting-result", "batting-result.ball", "pitch-event")


class FirstBallExecutionError(RuntimeError):
    """scope/host/未提供投影を、恒久的な内容拒否へ畳まない。"""

    def __init__(self) -> None:
        """元例外や資格値を表示しない。"""
        super().__init__("初球実行の同一scopeを確認できません")


@dataclass(slots=True, repr=False)
class _Execution:
    handle: Any
    writer: PortWriter
    source: _E1CoreSource
    event: SyncEvent
    runtime: object
    lifetime: tuple[object, object]
    context: TenantContext
    bound: _LiveWriterBinding
    lease: object
    source_phase: object
    snapshot: str
    nonce: bytes
    event_fingerprint: str
    phase: str = "preparing"
    bridge: FirstBallBridge | None = None
    frame: FirstBallFrame | None = None
    payload: FirstBallPayloadValue | None = None


_EXECUTIONS: dict[object, _Execution] = {}


def _live(state: _Execution) -> None:
    """Actual runtime/writer/source/phase/nonceを各境界で再確認する。"""
    handle, writer, source, bound = (
        state.handle,
        state.writer,
        state.source,
        state.bound,
    )
    key = handle._state_key
    if (
        type(handle) is not transaction._TenantTransaction
        or _EXECUTIONS.get(key) is not state
        or transaction._TRANSACTION_RUNTIMES.get(key) is not state.runtime
        or transaction._SYNC_APPLY_ACTIVE.get() is not True
        or handle._context is not state.context
        or type(state.context) is not TenantContext
        or handle._bound_tenant_id != state.context.tenant_id
        or handle._bound_integrity_proof != state.context._integrity_proof
        or not state.context._has_valid_integrity_proof()
        or type(writer) is not PortWriter
        or writer._active is not True
        or getattr(writer._execute, "__self__", None) is not handle
        or getattr(writer._execute, "__func__", None)
        is not transaction._TenantTransaction.run
        or type(source) is not _E1CoreSource
        or source.scope is not handle
        or source.context is not state.context
        or source.event is not state.event
        or source.phase is not state.source_phase
        or source.bound is not bound
        or type(bound) is not _LiveWriterBinding
        or _LIVE_BINDINGS.get(key) is not bound
        or bound._handle is not handle
        or bound._used
        or bound._lease is not state.lease
        or bound._phase_snapshot != state.snapshot
        or bound._lease._phase_snapshot != state.snapshot
        or type(bound._lease.nonce) is not bytes
        or bound._lease.nonce != state.nonce
    ):
        raise FirstBallExecutionError
    handle._assert_writer_lifetime(state.lifetime)
    view = source.read(handle, state.event)
    if view.event_fingerprint != state.event_fingerprint:
        raise FirstBallExecutionError
    handle._assert_writer_lifetime(state.lifetime)


def _participants(raw: str) -> FirstBallParticipants:
    """既artifactの射影の一意な打順/守備参照を取り出すだけ。配置を計算しない。"""
    roster = InitialRosterProjection.model_validate_json(raw)
    away, home = roster.teams
    batters = [
        entry
        for entry in away.participants
        if entry.batting_slot.kind == "slot" and entry.batting_slot.slot == "1"
    ]
    pitchers = [
        entry
        for entry in home.participants
        if any(role.kind == "fielding" and role.position == "1" for role in entry.roles)
    ]
    catchers = [
        entry
        for entry in home.participants
        if any(role.kind == "fielding" and role.position == "2" for role in entry.roles)
    ]
    if len(batters) != 1 or len(pitchers) != 1 or len(catchers) != 1:
        raise FirstBallExecutionError
    return FirstBallParticipants(
        batterId=batters[0].player.player_id,
        pitcherId=pitchers[0].player.player_id,
        catcherId=catchers[0].player.player_id,
        battingOrder="1",
    )


def _raw(value: object) -> str:
    """既JSON写像だけを使い、wire指紋や観測値を作り直さない。"""
    return json.dumps(
        _json_value(value), ensure_ascii=False, sort_keys=True, allow_nan=False
    )


@contextmanager
def _bind_first_ball_execution(handle, writer, event, source):
    """⑤/⑥/W2後の核だけが使う。content Portの外で実評価を一回保持する。"""
    if (
        type(handle) is not transaction._TenantTransaction
        or type(writer) is not PortWriter
        or type(event) is not SyncEvent
        or type(source) is not _E1CoreSource
        or handle._state_key in _EXECUTIONS
        or transaction._port_phase(handle) is not None
        or source.write_started
    ):
        raise FirstBallExecutionError
    key = handle._state_key
    bound = source.bound
    if (
        type(bound) is not _LiveWriterBinding
        or type(bound._lease.nonce) is not bytes
        or len(bound._lease.nonce) != 32
    ):
        raise FirstBallExecutionError
    view = source.read(handle, event)
    state = _Execution(
        handle,
        writer,
        source,
        event,
        transaction._TRANSACTION_RUNTIMES.get(key),
        handle._writer_lifetime(),
        handle._context,
        bound,
        bound._lease,
        source.phase,
        bound._phase_snapshot,
        bound._lease.nonce,
        view.event_fingerprint,
    )
    _EXECUTIONS[key] = state
    try:
        _live(state)
        with ExitStack() as stack:
            raw_v7, raw_v8 = None, None
            try:
                raw_v7, raw_v8 = _raw(event.v7), _raw(event.v8)
                # 型の事前判定だけ。client計算値を数学の期待値には使わない。
                supplied = FirstBallPlayPayload.model_validate_json(
                    raw_v7, by_alias=True, by_name=False
                )
                client_request = supplied.calculation.request.t1
                if (
                    client_request.event_kind,
                    client_request.result_id,
                    client_request.pitch_event_kind,
                ) != (_INTENT.event_kind, _INTENT.result_id, _INTENT.pitch_event_kind):
                    raise ValueError
            except (TypeError, ValueError, RecursionError):
                state.phase = "rejected"
            if state.phase != "rejected":
                if type(raw_v7) is not str or type(raw_v8) is not str:
                    raise FirstBallExecutionError
                bridge = stack.enter_context(
                    _bind_e1_first_ball_at_content_stage(
                        handle, writer, event, source=source
                    )
                )
                # 期待identity。実使用証拠は既bridgeの同host._sourceとの一致が所有する。
                expected_hash = hashlib.sha256(
                    _verified_source(*_product_artifact_paths()).encode("utf-8")
                ).hexdigest()
                try:
                    frame = evaluate_first_ball_frame(
                        bridge,
                        _INTENT,
                        writer=writer,
                        event=event,
                        expected_artifact_sha256=expected_hash,
                    )
                except FirstBallContentRejected:
                    state.phase = "rejected"
                else:
                    _live(state)
                    value = _read_ready_first_ball_frame(
                        bridge, frame, writer=writer, event=event
                    )
                    request = CombinedRequest.model_validate_json(value.request_json)
                    response = decode_combined_response(value.response_json)
                    if type(response) is not CombinedSuccess:
                        raise FirstBallExecutionError
                    calculation = FirstBallCalculationValue.model_validate_json(
                        format_first_ball_calculation(
                            request, response, artifact_sha256=value.artifact_sha256
                        )
                    )
                    people = _participants(value.roster_json)
                    try:
                        state.payload = read_first_ball_payload(
                            raw_v7,
                            raw_v8,
                            expected_calculation=calculation,
                            expected_participants=people,
                        )
                    except FirstBallPayloadError:
                        state.phase = "rejected"
                    else:
                        state.bridge, state.frame, state.phase = bridge, frame, "ready"
            _live(state)
            yield
    finally:
        if _EXECUTIONS.get(key) is state:
            del _EXECUTIONS[key]
        state.phase, state.bridge, state.frame, state.payload = (
            "closed",
            None,
            None,
            None,
        )


def _validate_first_ball_command(handle, operation) -> TenantOperationResult:
    """Portには固定bool/reasonだけ返し、payload/context/frameを貸与しない。"""
    state = _EXECUTIONS.get(handle._state_key)
    if (
        type(state) is not _Execution
        or type(operation) is not PortValidateFirstBallToken
    ):
        raise FirstBallExecutionError
    _live(state)
    phase = transaction._port_phase(handle)
    if (
        phase is None
        or phase.kind != "content"
        or phase.handle is not handle
        or phase.bound is not state.bound
        or phase.snapshot != state.snapshot
        or state.source.write_started
        or operation.writer is not state.writer
        or operation.event is not state.event
        or type(operation.game_id) is not UUID
        or type(operation.d5) is not UUID
        or operation.game_id != UUID(state.event.game_id)
        or operation.d5 != UUID(state.event.d5)
        or state.phase not in ("ready", "rejected")
    ):
        raise FirstBallExecutionError
    if state.phase == "ready":
        if (
            type(state.bridge) is not FirstBallBridge
            or type(state.frame) is not FirstBallFrame
        ):
            raise FirstBallExecutionError
        _read_ready_first_ball_frame(
            state.bridge, state.frame, writer=state.writer, event=state.event
        )
    return TenantOperationResult(
        ((state.phase == "ready", None if state.phase == "ready" else _REASON),)
    )


def _require_first_ball_projection_completed(handle, event) -> None:
    """単位Bの正式consume/投影が未提供なら、成功へ補完せず全rollbackする。"""
    state = _EXECUTIONS.get(handle._state_key)
    if state is None:
        raise FirstBallExecutionError
    _live(state)
    if event.d5 != state.event.d5 or state.phase != "projected":
        raise FirstBallExecutionError
