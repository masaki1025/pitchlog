"""origin選択境界。E1真正issuerは未供給で閉拒否する。

legacy専用私有入口は実Contextと同requestを寿命へ束縛する。E1の自由な
registry登録APIは提供せず、pure登録doubleを実受付の証拠とはしない。
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pitchlog.repositories.context import TenantContext
from pitchlog.sync.idempotency import (
    _EVENT_SOURCE_FIELDS,
    RegistrationSource,
    event_source,
    operation_fingerprint,
)
from pitchlog.sync.model import ABSENT, SyncEvent, SyncRequest
from pitchlog.sync.wire_fingerprint import WireEventValue, wire_event_fingerprint
from pitchlog.sync.wire_original import _canonical, encode_wire_original
from pitchlog.sync.wire_source import WireSourceValue, checked_wire_source

_ERROR = "E-1又はlegacyの発行済みsourceを利用できません"


class SourceBindingError(ValueError):
    """原値・参照・元例外を表示しない固定の拒否。"""


class LegacyEntryScope:
    """専用legacy私有入口の寿命だけで有効な参照。"""

    __slots__ = ()

    def __new__(cls) -> LegacyEntryScope:
        """自由生成を拒否する。"""
        raise SourceBindingError(_ERROR)


class E1Receipt:
    """E-1実受付の私有参照。pure sourceのsealで代用しない。"""

    __slots__ = ()

    def __new__(cls) -> E1Receipt:
        """自由生成を拒否する。"""
        raise SourceBindingError(_ERROR)


class EventSourceBinding:
    """当該request/eventへ固定した選択参照。自由digestを保持しない。"""

    __slots__ = ()

    def __new__(cls) -> EventSourceBinding:
        """自由生成を拒否する。"""
        raise SourceBindingError(_ERROR)


@dataclass(slots=True, repr=False)
class _LegacyState:
    """専用legacy私有入口が保持する状態。E1へ転用しない。"""

    request: SyncRequest
    request_json: str
    registrations: tuple[RegistrationSource | None, ...]
    fingerprints: tuple[str, ...]
    active: bool
    # 旧getterは変更しない。3Bの専用実entryが束縛するまで新accessorは拒否。
    context: TenantContext | None = None


@dataclass(slots=True, repr=False)
class _ReceiptState:
    """request lifetimeの状態形。context証跡は実認証の代替ではない。"""

    context: TenantContext
    tenant_id: UUID
    request: SyncRequest
    request_json: str
    source: WireSourceValue
    active: bool
    # U11の同HTTP/request issuerが発行するまで未発行。Noneから成功推定しない。
    device_presentation: object = None


@dataclass(frozen=True, slots=True, repr=False)
class _Selection:
    """originはcaller引数ではなく私有ownerの実型により固定する。"""

    owner: LegacyEntryScope | E1Receipt
    state: _LegacyState | _ReceiptState
    event: SyncEvent
    position: int
    fingerprint: str
    request: SyncRequest
    source: WireSourceValue | None
    context: TenantContext | None
    registration: RegistrationSource | None
    entry_context: TenantContext | None = None


# 後続issuerの実装なし。unit testの直接登録はpure状態機械のdoubleに限る。
_LEGACY: dict[LegacyEntryScope, _LegacyState] = {}
_RECEIPTS: dict[E1Receipt, _ReceiptState] = {}
_SELECTIONS: dict[EventSourceBinding, _Selection] = {}


def _request_json(request: SyncRequest) -> str:
    """同requestの全値を再照合するsnapshot。D5指紋の算式ではない。"""
    if type(request) is not SyncRequest or type(request.events) is not tuple:
        raise ValueError(_ERROR)
    raw: dict[str, object] = {
        "path": request.path,
        "game_id": request.game_id,
        "d4": request.d4,
        "events": [event_source(event) for event in request.events],
    }
    if any(type(event) is not SyncEvent for event in request.events):
        raise ValueError(_ERROR)
    if request.v12 is not ABSENT:
        raw["v12"] = request.v12
    if request.recovery_generation is not ABSENT:
        raw["recovery_generation"] = request.recovery_generation
    return _canonical(raw)


def _legacy(owner: LegacyEntryScope) -> _LegacyState:
    """既式と登録値の全値を再検査し、E-1参照の転用を拒否する。"""
    if type(owner) is not LegacyEntryScope:
        raise ValueError(_ERROR)
    state = _LEGACY[owner]
    if (
        type(state) is not _LegacyState
        or state.active is not True
        or _request_json(state.request) != state.request_json
        or type(state.registrations) is not tuple
        or type(state.fingerprints) is not tuple
        or len(state.request.events) != len(state.registrations)
        or len(state.fingerprints) != len(state.registrations)
    ):
        raise ValueError(_ERROR)
    for event, registration, digest in zip(
        state.request.events, state.registrations, state.fingerprints, strict=True
    ):
        if (
            type(digest) is not str
            or operation_fingerprint(event, state.request.path, registration) != digest
        ):
            raise ValueError(_ERROR)
    return state


def _receipt(owner: E1Receipt) -> _ReceiptState:
    """原wire値だけで受付を発行せず、登録済みcontext/scopeを再照合。"""
    if type(owner) is not E1Receipt:
        raise ValueError(_ERROR)
    state = _RECEIPTS.get(owner)
    if (
        type(state) is not _ReceiptState
        or state.active is not True
        or type(state.context) is not TenantContext
        or type(state.tenant_id) is not UUID
        or not state.context._has_valid_integrity_proof()
        or state.context.tenant_id != state.tenant_id
        or _request_json(state.request) != state.request_json
    ):
        raise ValueError(_ERROR)
    source = checked_wire_source(state.source)
    if (
        source.game_id != state.request.game_id
        or source.d4 != state.request.d4
        or len(source.events) != len(state.request.events)
    ):
        raise ValueError(_ERROR)
    for raw_event, event in zip(source.events, state.request.events, strict=True):
        # 原wireをDTOから再構成しない。共有全項目の値/欠落だけをstrict照合する。
        raw = raw_event.wire_event
        dto = event_source(event)
        known = {"game_id", "d4", "d1", "d5"} | {
            name for _, name in _EVENT_SOURCE_FIELDS
        }
        if _canonical({k: v for k, v in raw.items() if k in known}) != _canonical(dto):
            raise ValueError(_ERROR)
        if any(
            type(raw.get(key)) is not type(expected) or raw[key] != expected
            for key, expected in (
                ("game_id", event.game_id),
                ("d4", event.d4),
                ("d1", event.d1),
                ("d5", event.d5),
            )
        ):
            raise ValueError(_ERROR)
    return state


def _select(selection: _Selection) -> EventSourceBinding:
    """既に照合した状態の選択参照だけを作る。受付issuerではない。"""
    binding = object.__new__(EventSourceBinding)
    _SELECTIONS[binding] = selection
    return binding


def legacy_dto_source(
    entry: LegacyEntryScope,
    request: SyncRequest,
    event: SyncEvent,
    registration: RegistrationSource | None,
) -> EventSourceBinding:
    """私有legacy scopeがない限り旧式計算を呼ばない。"""
    try:
        state = _legacy(entry)
        if request is not state.request:
            raise ValueError(_ERROR)
        positions = [i for i, item in enumerate(request.events) if item is event]
        if len(positions) != 1:
            raise ValueError(_ERROR)
        position = positions[0]
        if registration is not state.registrations[position]:
            raise ValueError(_ERROR)
        return _select(
            _Selection(
                entry,
                state,
                event,
                position,
                state.fingerprints[position],
                request,
                None,
                None,
                registration,
                entry_context=state.context,
            )
        )
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise SourceBindingError(_ERROR) from None


def e1_event_source(receipt: E1Receipt, position: int) -> EventSourceBinding:
    """真正issuer未供給ではfail-closed。位置は原eventsの1始まり。"""
    try:
        state = _receipt(receipt)
        if type(position) is not int or not 1 <= position <= len(state.request.events):
            raise ValueError(_ERROR)
        index = position - 1
        return _select(
            _Selection(
                receipt,
                state,
                state.request.events[index],
                index,
                state.source.event_fingerprints[index],
                state.request,
                state.source,
                state.context,
                None,
            )
        )
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise SourceBindingError(_ERROR) from None


def selected_event_fingerprint(binding: EventSourceBinding, event: SyncEvent) -> str:
    """発行済み選択値を同request/event/registrationへ再照合する。"""
    try:
        if type(binding) is not EventSourceBinding:
            raise ValueError(_ERROR)
        selected = _SELECTIONS[binding]
        if type(selected) is not _Selection or event is not selected.event:
            raise ValueError(_ERROR)
        if type(selected.owner) is LegacyEntryScope:
            state = _legacy(selected.owner)
            digests = state.fingerprints
            if (
                type(selected.position) is not int
                or not 0 <= selected.position < len(state.registrations)
                or state.registrations[selected.position] is not selected.registration
                or selected.source is not None
                or selected.context is not None
            ):
                raise ValueError(_ERROR)
        elif type(selected.owner) is E1Receipt:
            state = _receipt(selected.owner)
            digests = state.source.event_fingerprints
            if (
                state.source is not selected.source
                or state.context is not selected.context
                or selected.registration is not None
            ):
                raise ValueError(_ERROR)
        else:
            raise ValueError(_ERROR)
        if (
            state is not selected.state
            or state.request is not selected.request
            or type(selected.position) is not int
            or not 0 <= selected.position < len(state.request.events)
            or state.request.events[selected.position] is not event
            or digests[selected.position] != selected.fingerprint
        ):
            raise ValueError(_ERROR)
        return selected.fingerprint
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise SourceBindingError(_ERROR) from None


@dataclass(frozen=True, slots=True, repr=False)
class SelectedEventSourceValue:
    """検証時点の純値。受付/認可/writer/保存の資格として再利用しない。"""

    origin: Literal["legacy", "e1"]
    position: int
    event_fingerprint: str
    request_fingerprint: str | None
    wire_event: WireEventValue | None
    wire_original_json: str | None


def read_selected_event_source(
    binding: EventSourceBinding,
    *,
    context: TenantContext,
    request: SyncRequest,
    event: SyncEvent,
) -> SelectedEventSourceValue:
    """元bindingを実callerへ再照合し、原位置とraw純値だけを返す。

    Args:
        binding: 専用入口に由来する私有選択参照。現単位にはissuerはない。
        context: 実kernelが同一要求で保持するcontext。値の同値では代用しない。
        request: 同じ要求実体。
        event: 同じ要求内の当該イベント実体。

    Returns:
        1始まりの原位置と指紋/原本純値。重要点で元bindingを再検査する必要がある。

    Raises:
        SourceBindingError: 未発行/失効/実caller不一致/原値変更の場合。
    """
    try:
        fingerprint = selected_event_fingerprint(binding, event)
        selected = _SELECTIONS[binding]
        if (
            type(context) is not TenantContext
            or not context._has_valid_integrity_proof()
            or type(request) is not SyncRequest
            or request is not selected.request
            or type(event) is not SyncEvent
            or event is not selected.event
            or request.events[selected.position] is not event
        ):
            raise ValueError(_ERROR)
        if type(selected.owner) is E1Receipt:
            receipt = _receipt(selected.owner)
            if (
                receipt is not selected.state
                or receipt.context is not context
                or selected.context is not context
                or receipt.request is not request
            ):
                raise ValueError(_ERROR)
            source = checked_wire_source(receipt.source)
            if source is not selected.source:
                raise ValueError(_ERROR)
            wire = source.events[selected.position]
            if wire_event_fingerprint(wire) != fingerprint:
                raise ValueError(_ERROR)
            value = SelectedEventSourceValue(
                "e1",
                selected.position + 1,
                fingerprint,
                source.request_fingerprint,
                wire,
                encode_wire_original(wire),
            )
        elif type(selected.owner) is LegacyEntryScope:
            legacy = _legacy(selected.owner)
            if (
                legacy is not selected.state
                or legacy.request is not request
                or legacy.context is not context
                or selected.entry_context is not context
            ):
                raise ValueError(_ERROR)
            value = SelectedEventSourceValue(
                "legacy",
                selected.position + 1,
                fingerprint,
                None,
                None,
                None,
            )
        else:
            raise ValueError(_ERROR)
        # JSON描画中を含む後発差替えを再確認。返却値自体は新資格ではない。
        if (
            _SELECTIONS[binding] is not selected
            or selected_event_fingerprint(binding, event) != fingerprint
            or request is not selected.request
        ):
            raise ValueError(_ERROR)
        if type(selected.owner) is E1Receipt:
            if _receipt(selected.owner).context is not context:
                raise ValueError(_ERROR)
        elif type(selected.owner) is LegacyEntryScope:
            if _legacy(selected.owner).context is not context:
                raise ValueError(_ERROR)
        else:
            raise ValueError(_ERROR)
        return value
    except (
        AttributeError,
        IndexError,
        KeyError,
        TypeError,
        ValueError,
        RecursionError,
    ):
        raise SourceBindingError(_ERROR) from None


@contextmanager
def _legacy_entry_scope(context, request, registrations):
    """実legacy入口のcontext/request寿命だけへ閉じる私有scope。

    E1 receiptは受けず、自由digestやoriginを入力にしない。認可は既③が所有し、
    このscope自体を認可資格としない。実E1 issuerの登録口は追加しない。
    """
    try:
        if (
            type(context) is not TenantContext
            or not context._has_valid_integrity_proof()
            or type(request) is not SyncRequest
        ):
            raise ValueError(_ERROR)
        values = tuple(registrations.get(event.d5) for event in request.events)
        digests = tuple(
            operation_fingerprint(event, request.path, registration)
            for event, registration in zip(request.events, values, strict=True)
        )
        state = _LegacyState(
            request, _request_json(request), values, digests, True, context
        )
        owner = object.__new__(LegacyEntryScope)
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise SourceBindingError(_ERROR) from None
    _LEGACY[owner] = state
    try:
        yield owner
    finally:
        state.active = False
        for key, selected in tuple(_SELECTIONS.items()):
            if selected.owner is owner:
                del _SELECTIONS[key]
        _LEGACY.pop(owner, None)


class _E1CoreSource:
    """実bound writerと元sourceの再検査口。純値だけから新資格を作らない。"""

    __slots__ = (
        "binding",
        "scope",
        "context",
        "request",
        "event",
        "phase",
        "bound",
        "write_started",
    )

    def __init__(self, binding, *, scope, context, request, event, phase, bound):
        from pitchlog.sync.control_provider.writer_binding import _LiveWriterBinding

        if (
            type(binding) is not EventSourceBinding
            or type(bound) is not _LiveWriterBinding
            or bound._handle is not scope
            or scope._context is not context
        ):
            raise SourceBindingError(_ERROR)
        self.binding, self.scope, self.context = binding, scope, context
        self.request, self.event, self.phase, self.bound = request, event, phase, bound
        self.write_started = False
        self.read(scope, event)

    def read(self, scope, event):
        """重要点ごとに同じ元bindingと同writerの現在値を照合する。"""
        if (
            scope is not self.scope
            or event is not self.event
            or self.bound._handle is not scope
            or scope._context is not self.context
        ):
            raise SourceBindingError(_ERROR)
        return self.bound.assert_event_source(
            self.binding,
            context=self.context,
            request=self.request,
            event=event,
            phase=self.phase,
        )

    def begin_write(self, scope, event):
        """最初の書込tokenより前にsourceを再確認して分岐を閉じる。"""
        self.read(scope, event)
        self.write_started = True
