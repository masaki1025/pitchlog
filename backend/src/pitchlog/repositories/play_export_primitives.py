"""唯一の登録operation経由でT5保存原本の有限pageを読む。"""

from __future__ import annotations

import re
import weakref
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from pitchlog.repositories import transaction as _transaction_runtime
from pitchlog.repositories.binding import TenantBindingError
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.stats.generated.receiver import METRIC_IDS, receive_fact_row


class PrimitiveReadError(ValueError):
    """sourceや資格を露出しない読取の固定拒否。"""


@dataclass(frozen=True, slots=True)
class _QualifiedStatsReadCall:
    """dispatcherだけが消費後に受け取る実命令と本物transaction ID。"""

    operation: TenantOperationToken
    transaction_id: str | None


@dataclass(slots=True)
class _ReaderState:
    """reader自身とは別に実handle/runtimeと発行済identityを記憶する。"""

    handle: _TenantTransaction
    state_key: object
    runtime: object
    key: object
    maximum_integer_chars: int
    receipts: dict = field(default_factory=dict)
    cursors: dict = field(default_factory=dict)


@dataclass(slots=True)
class _ReadCall:
    """実runの同期呼出し中だけ存在する一回資格。"""

    reader: ReadPlayExportPrimitives
    operation: TenantOperationToken
    values: tuple
    receipt: PrimitiveSnapshot | None
    cursor: PrimitiveCursor | None
    transaction_id: str | None
    consumed: bool = False


_READERS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_READ_CALLS: dict[object, _ReadCall] = {}


def _capture_values(values):
    """UUID本体のfrozen迂回書換えにも影響されない発行時値を保持する。"""
    return tuple(
        (type(value), value.int if type(value) is UUID else value) for value in values
    )


def _same_values(current, expected):
    """bool/int互換や偽等値を使わず、固定実型と発行時全値を照合する。"""
    return len(current) == len(expected) and all(
        type(value) is kind and (value.int if kind is UUID else value) == captured
        for value, (kind, captured) in zip(current, expected, strict=True)
    )


def _remember_identity(registry, value, facts):
    """同値cloneを受けず、解放済receipt/cursorの登録も蓄積させない。"""
    key = id(value)

    def discard(reference):
        entry = registry.get(key)
        if entry is not None and entry[0] is reference:
            registry.pop(key)

    registry[key] = (weakref.ref(value, discard), facts)


def _reader_state(reader):
    """実constructorが登録したreaderと現在のRRRO runtimeだけを受ける。"""
    if type(reader) is not ReadPlayExportPrimitives:
        raise PrimitiveReadError
    state = _READERS.get(reader)
    if state is None:
        raise PrimitiveReadError
    _require_root_read_scope(state.handle)
    if (
        reader._handle is not state.handle
        or reader._state_key is not state.state_key
        or state.handle._state_key is not state.state_key
        or _transaction_runtime._TRANSACTION_RUNTIMES.get(state.state_key)
        is not state.runtime
        or reader._key is not state.key
        or type(reader._maximum_integer_chars) is not int
        or reader._maximum_integer_chars != state.maximum_integer_chars
    ):
        raise PrimitiveReadError
    return state


def _scope_values(scope):
    """scopeの実型と元の固定三値を毎回確認する。"""
    if type(scope) is not PrimitiveScope:
        raise PrimitiveReadError
    PrimitiveScope.__post_init__(scope)
    return scope.game_id, scope.player_id, scope.model_sha256


def _receipt_values(receipt):
    """発行時から変更できないreceipt全値を読む。"""
    return (
        *_scope_values(receipt.scope),
        receipt.fact_version_id,
        receipt.revision,
        receipt.source_set_sha256,
        receipt.source_count,
        receipt.row_count,
        receipt.transaction_id,
        receipt.completion_state,
    )


def _require_receipt(reader, receipt):
    """実Open結果の同一receiptだけを同readerへ貸与する。"""
    state = _reader_state(reader)
    entry = state.receipts.get(id(receipt))
    if (
        type(receipt) is not PrimitiveSnapshot
        or entry is None
        or entry[0]() is not receipt
        or receipt._owner is not reader
        or receipt.scope is not entry[1][0]
        or not _same_values(_receipt_values(receipt), entry[1][1])
    ):
        raise PrimitiveReadError
    return state


def _require_cursor(reader, receipt, cursor):
    """実pageが発行したcursorのidentity・全値・receiptを照合する。"""
    state = _require_receipt(reader, receipt)
    if cursor is None:
        return
    entry = state.cursors.get(id(cursor))
    if (
        type(cursor) is not PrimitiveCursor
        or entry is None
        or entry[0]() is not cursor
        or cursor._binding is not receipt
        or entry[1][0]() is not receipt
    ):
        raise PrimitiveReadError
    PrimitiveCursor.__post_init__(cursor)
    if not _same_values(
        (cursor.d2, cursor.source_event_id, cursor.metric_id), entry[1][1]
    ):
        raise PrimitiveReadError


def _operation_values(operation):
    """値tokenの実型を固定し、受付後の書換えも検出する。"""
    from pitchlog.repositories.stats import ReadPrimitiveTotalsToken

    if type(operation) not in {
        OpenPrimitiveSnapshotToken,
        ReadPrimitivePageToken,
        ReadPrimitiveTotalsToken,
    }:
        raise PrimitiveReadError
    try:
        return tuple(
            getattr(operation, name) for name in operation.__dataclass_fields__
        )
    except AttributeError as error:
        raise PrimitiveReadError from error


def _check_read_values(reader, operation, receipt, cursor):
    """tokenの全値を発行済receipt/cursorへ束縛し、自由TX値を受けない。"""
    values = _operation_values(operation)
    if type(operation) is OpenPrimitiveSnapshotToken:
        if receipt is not None or cursor is not None:
            raise PrimitiveReadError
        PrimitiveScope(*values)
        return
    _require_cursor(reader, receipt, cursor)
    scope = receipt.scope
    expected = (
        scope.game_id,
        scope.player_id,
        receipt.fact_version_id,
        receipt.revision,
        receipt.source_set_sha256,
        scope.model_sha256,
    )
    if type(operation) is ReadPrimitivePageToken:
        if type(operation.page_size) is not int or not 1 <= operation.page_size <= 500:
            raise PrimitiveReadError
        expected += (
            cursor.d2 if cursor else None,
            cursor.source_event_id if cursor else None,
            cursor.metric_id if cursor else None,
            operation.page_size,
        )
    elif cursor is not None:
        raise PrimitiveReadError
    if not _same_values(values, _capture_values(expected)):
        raise PrimitiveReadError


@contextmanager
def _read_call(reader, operation, *, receipt=None, cursor=None):
    """readerの実run中だけ一回資格を配置し、例外時にも回収する。"""
    state = _reader_state(reader)
    if state.state_key in _READ_CALLS:
        raise PrimitiveReadError
    _check_read_values(reader, operation, receipt, cursor)
    call = _ReadCall(
        reader,
        operation,
        _capture_values(_operation_values(operation)),
        receipt,
        cursor,
        None if receipt is None else receipt.transaction_id,
    )
    _READ_CALLS[state.state_key] = call
    try:
        yield
        _reader_state(reader)
        if not call.consumed or not _same_values(
            _operation_values(operation), call.values
        ):
            raise PrimitiveReadError
        if receipt is not None:
            _require_cursor(reader, receipt, cursor)
    finally:
        if _READ_CALLS.get(state.state_key) is call:
            _READ_CALLS.pop(state.state_key)


def _qualified_stats_read_call(handle, operation) -> _QualifiedStatsReadCall:
    """同reader/runの実命令を一度だけ消費し、SQL前の資格を返す。"""
    if type(handle) is not _TenantTransaction:
        raise PrimitiveReadError
    _require_root_read_scope(handle)
    call = _READ_CALLS.get(handle._state_key)
    if call is None or call.consumed or call.operation is not operation:
        raise PrimitiveReadError
    state = _reader_state(call.reader)
    if state.handle is not handle or not _same_values(
        _operation_values(operation), call.values
    ):
        raise PrimitiveReadError
    _check_read_values(call.reader, operation, call.receipt, call.cursor)
    if call.receipt is not None:
        _require_cursor(call.reader, call.receipt, call.cursor)
        if call.transaction_id != call.receipt.transaction_id:
            raise PrimitiveReadError
    call.consumed = True
    return _QualifiedStatsReadCall(operation, call.transaction_id)


def _require_root_read_scope(handle):
    """rootの真正RR RO markerが未供給なら、通常scopeを代用品にしない。"""
    if (
        type(handle) is not _TenantTransaction
        or getattr(handle, "_state_key", None) is None
    ):
        raise PrimitiveReadError
    verify = getattr(_transaction_runtime, "_require_stats_primitive_read_scope", None)
    if not callable(verify):
        raise PrimitiveReadError
    try:
        verify(handle)
    except TenantBindingError as error:
        raise PrimitiveReadError from error


@dataclass(frozen=True, slots=True)
class PrimitiveScope:
    """呼出条件。自身は認可やsourceの真正性を証明しない。"""

    game_id: UUID
    player_id: UUID
    model_sha256: str

    def __post_init__(self):
        """自由文字列や近似値のscopeを拒否する。"""
        if (
            type(self.game_id) is not UUID
            or type(self.player_id) is not UUID
            or type(self.model_sha256) is not str
            or re.fullmatch(r"sha256:[a-f0-9]{64}", self.model_sha256) is None
        ):
            raise PrimitiveReadError


@dataclass(frozen=True, slots=True, weakref_slot=True)
class PrimitiveCursor:
    """window後の全tieを含むkeyset。"""

    d2: int
    source_event_id: UUID
    metric_id: str
    _binding: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        """SQL bigintegerと既知IDだけを受ける。"""
        if (
            type(self.d2) is not int
            or not -(2**63) <= self.d2 < 2**63
            or type(self.source_event_id) is not UUID
            or type(self.metric_id) is not str
            or self.metric_id not in METRIC_IDS
        ):
            raise PrimitiveReadError

    @property
    def ordering_key(self):
        """PostgreSQLと同じ論理tie順序を返す。"""
        return self.d2, self.source_event_id.int, self.metric_id


@dataclass(frozen=True, slots=True)
class OpenPrimitiveSnapshotToken(TenantOperationToken):
    """root登録済みread関数へ実scopeを渡す。"""

    game_id: UUID
    player_id: UUID
    model_sha256: str

    @property
    def capability_id(self):
        """自由capabilityを受けず固定読取能力を使う。"""
        return "CAP:stats_primitives:read"


@dataclass(frozen=True, slots=True)
class ReadPrimitivePageToken(TenantOperationToken):
    """同receiptの版/Sと有限cursorだけを渡す。"""

    game_id: UUID
    player_id: UUID
    fact_version_id: UUID
    revision: int
    source_set_sha256: str
    model_sha256: str
    after_d2: int | None
    after_source_event_id: UUID | None
    after_metric_id: str | None
    page_size: int

    @property
    def capability_id(self):
        """登録された固定能力を返す。"""
        return "CAP:stats_primitives:read"


@dataclass(frozen=True, slots=True, init=False, weakref_slot=True)
class PrimitiveSnapshot:
    """登録operationの実結果を同reader/handleへ束縛した短命receipt。"""

    scope: PrimitiveScope
    fact_version_id: UUID
    revision: int
    source_set_sha256: str
    source_count: int
    row_count: int
    transaction_id: str
    completion_state: str
    _owner: object

    def __init__(self, *, _owner, _key, scope, row):
        """constructorの値やownerの私有keyだけではreceiptを発行しない。"""
        raise PrimitiveReadError


@dataclass(frozen=True, slots=True)
class PrimitivePage:
    """1pageだけの完成表示値と最後のkeyset。"""

    rows: tuple[dict, ...]
    next_cursor: PrimitiveCursor | None


def _decode_page(rows, cursor, page_size, maximum_integer_chars, *, binding=None):
    """有限SQL行を生成receiverへ渡し、keyset逆行/重複を拒否する。"""
    if type(rows) is not tuple or len(rows) > page_size:
        raise PrimitiveReadError
    result = []
    last = cursor
    for row in rows:
        if type(row) is not tuple or len(row) != 5:
            raise PrimitiveReadError
        metric, state, amount, d2, event = row
        next_key = PrimitiveCursor(d2, event, metric, _binding=binding)
        if last is not None and next_key.ordering_key <= last.ordering_key:
            raise PrimitiveReadError
        if amount is not None and type(amount) not in (Decimal, str, int):
            raise PrimitiveReadError
        value = receive_fact_row(
            {"metric_id": metric, "state": state, "value": amount},
            maximum_integer_chars=maximum_integer_chars,
        )
        result.append({**value, "d2": d2, "source_event_id": event})
        last = next_key
    return PrimitivePage(tuple(result), last if rows else None)


class ReadPlayExportPrimitives:
    """実tenant handleの登録read operationだけを呼ぶ唯一reader。"""

    __slots__ = (
        "_handle",
        "_state_key",
        "_key",
        "_maximum_integer_chars",
        "__weakref__",
    )

    def __init__(self, handle, *, maximum_integer_chars):
        """rootの同snapshot scopeで開始された実handleだけを保持する。"""
        if (
            type(handle) is not _TenantTransaction
            or getattr(handle, "_state_key", None) is None
        ):
            raise PrimitiveReadError
        _require_root_read_scope(handle)
        if type(maximum_integer_chars) is not int or maximum_integer_chars < 1:
            raise PrimitiveReadError
        self._handle = handle
        self._state_key = handle._state_key
        self._key = object()
        self._maximum_integer_chars = maximum_integer_chars
        _READERS[self] = _ReaderState(
            handle,
            handle._state_key,
            _transaction_runtime._TRANSACTION_RUNTIMES[handle._state_key],
            self._key,
            maximum_integer_chars,
        )

    def _live(self):
        """scope終了/別handleへのreceipt流用を拒否する。"""
        _reader_state(self)

    def open(self, scope: PrimitiveScope):
        """実registered operationのCOUNT/版/Sからreceiptを発行する。"""
        self._live()
        scope_values = _capture_values(_scope_values(scope))
        operation = OpenPrimitiveSnapshotToken(
            scope.game_id, scope.player_id, scope.model_sha256
        )
        with _read_call(self, operation):
            result = self._handle.run(operation)
        if (
            not _same_values(_scope_values(scope), scope_values)
            or type(result) is not TenantOperationResult
            or len(result.rows) != 1
            or type(result.rows[0]) is not tuple
            or len(result.rows[0]) != 8
        ):
            raise PrimitiveReadError
        version, revision, digest, model, count, rows, tx, completion = result.rows[0]
        if (
            type(version) is not UUID
            or type(revision) is not int
            or revision < 1
            or type(digest) is not str
            or re.fullmatch(r"[a-f0-9]{64}", digest) is None
            or type(model) is not str
            or model != scope.model_sha256
            or type(count) is not int
            or count < 0
            or type(rows) is not int
            or rows < 0
            or type(tx) is not str
            or not tx
            or type(completion) is not str
            or completion not in ("current_open", "confirmed_ended")
        ):
            raise PrimitiveReadError
        receipt = object.__new__(PrimitiveSnapshot)
        for name, value in {
            "scope": scope,
            "fact_version_id": version,
            "revision": revision,
            "source_set_sha256": digest,
            "source_count": count,
            "row_count": rows,
            "transaction_id": tx,
            "completion_state": completion,
            "_owner": self,
        }.items():
            object.__setattr__(receipt, name, value)
        state = _reader_state(self)
        _remember_identity(
            state.receipts, receipt, (scope, _capture_values(_receipt_values(receipt)))
        )
        return receipt

    def read_page(self, receipt, *, cursor=None, page_size=500):
        """同receiptのwindow後を有限取得し、アプリで再集計しない。"""
        self._live()
        state = _require_receipt(self, receipt)
        if type(page_size) is not int or not 1 <= page_size <= 500:
            raise PrimitiveReadError
        _require_cursor(self, receipt, cursor)
        scope = receipt.scope
        operation = ReadPrimitivePageToken(
            scope.game_id,
            scope.player_id,
            receipt.fact_version_id,
            receipt.revision,
            receipt.source_set_sha256,
            scope.model_sha256,
            cursor.d2 if cursor else None,
            cursor.source_event_id if cursor else None,
            cursor.metric_id if cursor else None,
            page_size,
        )
        with _read_call(self, operation, receipt=receipt, cursor=cursor):
            result = self._handle.run(operation)
        if type(result) is not TenantOperationResult:
            raise PrimitiveReadError
        page = _decode_page(
            result.rows, cursor, page_size, self._maximum_integer_chars, binding=receipt
        )
        if page.next_cursor is not None:
            current = page.next_cursor
            _remember_identity(
                state.cursors,
                current,
                (
                    weakref.ref(receipt),
                    _capture_values(
                        (current.d2, current.source_event_id, current.metric_id)
                    ),
                ),
            )
        return page

    def pages(self, receipt, *, page_size=500):
        """同DB COUNTに一致する有限pageを逐次返し、全件list化しない。"""
        self._live()
        _require_receipt(self, receipt)
        if type(page_size) is not int or not 1 <= page_size <= 500:
            raise PrimitiveReadError
        consumed = 0
        cursor = None
        while consumed < receipt.row_count:
            page = self.read_page(receipt, cursor=cursor, page_size=page_size)
            if not page.rows or consumed + len(page.rows) > receipt.row_count:
                raise PrimitiveReadError
            consumed += len(page.rows)
            cursor = page.next_cursor
            yield page
