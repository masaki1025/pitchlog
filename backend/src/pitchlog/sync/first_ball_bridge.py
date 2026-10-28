"""⑦だけがbindする同writerの初期read・一回評価・私有frame。

未接続のprivileged部品。D5/認可/権利の判定を代行しない。後続kernelは既先行
拒否を完了してから本bindを使う。registered Portからの推移importは禁止する。
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Literal, cast
from uuid import UUID

from pitchlog.domainrt.first_pitch import FirstPitchRequest
from pitchlog.domainrt.first_pitch_continuation import (
    CombinedRequest,
    CombinedSuccess,
    _check_frozen_members,
    decode_combined_response,
)
from pitchlog.domainrt.host import NodeDomainHost, open_domain_host
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.started_snapshot import (
    StartedInitialSnapshot,
    read_initial_started_snapshot,
)
from pitchlog.repositories.transaction import (
    _SYNC_APPLY_ACTIVE,
    _TRANSACTION_RUNTIMES,
    _TenantTransaction,
)
from pitchlog.sync.first_ball_frame import (
    FirstBallBridge,
    FirstBallFrame,
    FirstBallFrameError,
    FirstBallFrameValue,
    FirstBallIntent,
)
from pitchlog.sync.idempotency import operation_fingerprint
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter

_LEGACY_BRIDGE_SOURCE = object()


@dataclass(slots=True, repr=False)
class _State:
    handle: _TenantTransaction
    writer: PortWriter
    key: object
    runtime: object
    lifetime: tuple[object, object]
    tenant: UUID
    event: SyncEvent
    fingerprint: str
    source: object
    phase: Literal["waiting", "evaluating", "ready", "consumed", "closed"] = "waiting"
    frame: FirstBallFrame | None = None
    value: FirstBallFrameValue | None = None


_STATES: dict[FirstBallBridge, _State] = {}
# 私有の同TX内重複評価防止。DBのD5消費/確定結果ではない。
_ATTEMPTED: dict[object, set[UUID]] = {}


def _fingerprint(event: SyncEvent, source: object, handle: _TenantTransaction) -> str:
    """原wire/既P2指紋だけを保持し、新しい指紋式を作らない。"""
    if (
        type(event) is not SyncEvent
        or type(event.d1) is not int
        or event.d1 != 1
        or type(event.v5) is not str
        or event.v5 != "1"
    ):
        raise FirstBallFrameError
    for value in (event.d5, event.game_id):
        if type(value) is not str or str(UUID(value)) != value:
            raise FirstBallFrameError
    if source is _LEGACY_BRIDGE_SOURCE:
        return operation_fingerprint(event, "P2", None)
    from pitchlog.sync.source_binding import _E1CoreSource

    if type(source) is not _E1CoreSource:
        raise FirstBallFrameError
    return source.read(handle, event).event_fingerprint


def _live(state: _State, writer: PortWriter, event: SyncEvent) -> None:
    """同じ生存scopeと実writer発行元を前後で確認する。"""
    handle = state.handle
    if (
        type(handle) is not _TenantTransaction
        or type(writer) is not PortWriter
        or writer is not state.writer
        or writer._active is not True
        or _SYNC_APPLY_ACTIVE.get() is not True
        or handle._state_key is not state.key
        or _TRANSACTION_RUNTIMES.get(state.key) is not state.runtime
        or type(handle._context) is not TenantContext
        or handle._bound_tenant_id != state.tenant
        or handle._context.tenant_id != state.tenant
        or handle._bound_integrity_proof != handle._context._integrity_proof
        or not handle._context._has_valid_integrity_proof()
        or getattr(writer._execute, "__self__", None) is not handle
        or getattr(writer._execute, "__func__", None) is not _TenantTransaction.run
        or _fingerprint(event, state.source, handle) != state.fingerprint
        or event.d5 != state.event.d5
        or event.game_id != state.event.game_id
    ):
        raise FirstBallFrameError
    handle._assert_writer_lifetime(state.lifetime)


def _state(bridge: FirstBallBridge, writer: PortWriter, event: SyncEvent) -> _State:
    """手作りbridgeを含め、私有registryに無い参照を拒否する。"""
    if type(bridge) is not FirstBallBridge:
        raise FirstBallFrameError
    state = _STATES.get(bridge)
    if state is None:
        raise FirstBallFrameError
    _live(state, writer, event)
    return state


@contextmanager
def _bind_first_ball_at_content_stage(
    handle: _TenantTransaction, writer: PortWriter, event: SyncEvent
) -> Iterator[FirstBallBridge]:
    """既先行拒否後の核だけが使う待機bind。read/計算はまだしない。

    外部のpassed_guards bool・callback・偽のwriter発行入口は受け取らない。
    ここで権利判定済みとは証明しない。後続kernelの⑦だけへ接合する。
    """
    with _bind_source_first_ball(
        handle, writer, event, source=_LEGACY_BRIDGE_SOURCE
    ) as bridge:
        yield bridge


@contextmanager
def _bind_e1_first_ball_at_content_stage(
    handle: _TenantTransaction, writer: PortWriter, event: SyncEvent, *, source: object
) -> Iterator[FirstBallBridge]:
    """E1の実sourceを必須とする私有bind。未接続Portの代用にはしない。"""
    from pitchlog.sync.source_binding import _E1CoreSource

    if type(source) is not _E1CoreSource:
        raise FirstBallFrameError
    with _bind_source_first_ball(handle, writer, event, source=source) as bridge:
        yield bridge


@contextmanager
def _bind_source_first_ball(handle, writer, event, *, source):
    """明示入口のsourceを保持し、frameの寿命全体で再照合する。"""
    bridge = object.__new__(FirstBallBridge)
    try:
        if type(handle) is not _TenantTransaction or type(writer) is not PortWriter:
            raise FirstBallFrameError
        key = handle._state_key
        if key is None or key not in _TRANSACTION_RUNTIMES:
            raise FirstBallFrameError
        tenant = handle._bound_tenant_id
        if type(tenant) is not UUID:
            raise FirstBallFrameError
        state = _State(
            handle,
            writer,
            key,
            _TRANSACTION_RUNTIMES[key],
            handle._writer_lifetime(),
            tenant,
            event,
            _fingerprint(event, source, handle),
            source,
        )
        _live(state, writer, event)
    except Exception:
        raise FirstBallFrameError from None
    for expired in tuple(_ATTEMPTED):
        if expired not in _TRANSACTION_RUNTIMES:
            del _ATTEMPTED[expired]
    _STATES[bridge] = state
    try:
        yield bridge
    finally:
        # 呼出元のO4/DB故障等は別の例外へ変換せず、そのまま伝播する。
        _STATES.pop(bridge, None)
        state.phase, state.frame, state.value = "closed", None, None


def evaluate_first_ball_frame(
    bridge: FirstBallBridge,
    intent: FirstBallIntent,
    *,
    writer: PortWriter,
    event: SyncEvent,
    expected_artifact_sha256: str,
) -> FirstBallFrame:
    """実初期readerと同じ検証済hostの一回評価からだけframeを発行する。"""
    state = None
    try:
        state = _state(bridge, writer, event)
        if state.phase != "waiting" or type(intent) is not FirstBallIntent:
            raise FirstBallFrameError
        if any(
            type(value) is not str
            for value in (intent.event_kind, intent.result_id, intent.pitch_event_kind)
        ):
            raise FirstBallFrameError
        if (
            type(expected_artifact_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected_artifact_sha256) is None
        ):
            raise FirstBallFrameError
        attempted = _ATTEMPTED.setdefault(state.key, set())
        if UUID(event.d5) in attempted:
            raise FirstBallFrameError
        attempted.add(UUID(event.d5))
        state.phase = "evaluating"
        snapshot = read_initial_started_snapshot(state.handle, UUID(event.game_id))
        _live(state, writer, event)
        if (
            type(snapshot) is not StartedInitialSnapshot
            or snapshot.tenant_id != state.tenant
            or snapshot.game_id != UUID(event.game_id)
            or type(snapshot.generation) is not int
            or snapshot.generation <= 0
            or type(snapshot.applied_prefix) is not int
            or snapshot.applied_prefix != 0
            or type(snapshot.confirmed_watermark) is not int
            or snapshot.confirmed_watermark != 0
        ):
            raise FirstBallFrameError
        request = CombinedRequest(
            t1=FirstPitchRequest(
                eventKind=intent.event_kind,
                resultId=intent.result_id,
                pitchEventKind=intent.pitch_event_kind,
                before=snapshot.before,
            ),
            rules=snapshot.rules,
        )
        _check_frozen_members(request)
        request = CombinedRequest.model_validate(request)
        with open_domain_host() as host:
            if type(host) is not NodeDomainHost or type(host._source) is not str:
                raise FirstBallFrameError
            source = host._source
            digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
            if digest != expected_artifact_sha256:
                raise FirstBallFrameError
            _live(state, writer, event)
            response = decode_combined_response(
                host.call(
                    "deriveFirstPitchWithContinuation",
                    request.model_dump_json(by_alias=True),
                )
            )
            if type(host._source) is not str or host._source != source:
                raise FirstBallFrameError
        _live(state, writer, event)
        if state.phase != "evaluating" or type(response) is not CombinedSuccess:
            raise FirstBallFrameError
        _check_frozen_members(response)
        response = CombinedSuccess.model_validate(response)
        value = FirstBallFrameValue(
            state.tenant,
            snapshot.game_id,
            snapshot.generation,
            cast(int, event.d1),
            UUID(event.d5),
            state.fingerprint,
            digest,
            request.model_dump_json(by_alias=True),
            response.model_dump_json(by_alias=True),
            snapshot.roster.model_dump_json(by_alias=True),
        )
        frame = object.__new__(FirstBallFrame)
        state.value, state.frame, state.phase = value, frame, "ready"
        return frame
    except Exception:
        if state is None and type(bridge) is FirstBallBridge:
            state = _STATES.get(bridge)
        if state is not None:
            state.phase, state.frame, state.value = "closed", None, None
        raise FirstBallFrameError from None


def consume_first_ball_frame(
    bridge: FirstBallBridge,
    frame: FirstBallFrame,
    *,
    writer: PortWriter,
    event: SyncEvent,
) -> FirstBallFrameValue:
    """同じ原event/writerの発行済frameを一度だけ取り出す。保存はしない。"""
    state = None
    try:
        state = _state(bridge, writer, event)
        if (
            state.phase != "ready"
            or type(frame) is not FirstBallFrame
            or frame is not state.frame
            or state.value is None
        ):
            raise FirstBallFrameError
        value = replace(state.value)
        state.phase, state.frame, state.value = "consumed", None, None
        return value
    except Exception:
        if state is None and type(bridge) is FirstBallBridge:
            state = _STATES.get(bridge)
        if state is not None:
            state.phase, state.frame, state.value = "closed", None, None
        raise FirstBallFrameError from None
