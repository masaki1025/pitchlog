"""唯一の登録operation経由でT5保存原本の有限pageを読む。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from pitchlog.repositories import transaction as _transaction_runtime
from pitchlog.repositories.binding import TenantBindingError
from pitchlog.repositories.tokens import TenantOperationToken
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.stats.generated.receiver import METRIC_IDS, receive_fact_row


class PrimitiveReadError(ValueError):
    """sourceや資格を露出しない読取の固定拒否。"""


def _require_root_read_scope(handle):
    """rootの真正RR RO markerが未供給なら、通常scopeを代用品にしない。"""
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


@dataclass(frozen=True, slots=True)
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


@dataclass(frozen=True, slots=True, init=False)
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
        """本readerの発行経路以外からのreceipt構築を拒否する。"""
        if type(_owner) is not ReadPlayExportPrimitives or _key is not _owner._key:
            raise PrimitiveReadError
        (
            version,
            revision,
            digest,
            model,
            source_count,
            row_count,
            transaction,
            completion,
        ) = row
        if (
            type(version) is not UUID
            or type(revision) is not int
            or revision < 1
            or type(digest) is not str
            or re.fullmatch(r"[a-f0-9]{64}", digest) is None
            or model != scope.model_sha256
            or type(source_count) is not int
            or source_count < 0
            or type(row_count) is not int
            or row_count < 0
            or type(transaction) is not str
            or not transaction
            or completion not in ("current_open", "confirmed_ended")
        ):
            raise PrimitiveReadError
        for name, value in {
            "scope": scope,
            "fact_version_id": version,
            "revision": revision,
            "source_set_sha256": digest,
            "source_count": source_count,
            "row_count": row_count,
            "transaction_id": transaction,
            "completion_state": completion,
            "_owner": _owner,
        }.items():
            object.__setattr__(self, name, value)


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

    __slots__ = ("_handle", "_state_key", "_key", "_maximum_integer_chars")

    def __init__(self, handle, *, maximum_integer_chars):
        """rootの同snapshot scopeで開始された実handleだけを保持する。"""
        if type(handle) is not _TenantTransaction or handle._state_key is None:
            raise PrimitiveReadError
        _require_root_read_scope(handle)
        if type(maximum_integer_chars) is not int or maximum_integer_chars < 1:
            raise PrimitiveReadError
        self._handle = handle
        self._state_key = handle._state_key
        self._key = object()
        self._maximum_integer_chars = maximum_integer_chars

    def _live(self):
        """scope終了/別handleへのreceipt流用を拒否する。"""
        _require_root_read_scope(self._handle)
        if self._handle._state_key is not self._state_key:
            raise PrimitiveReadError

    def open(self, scope: PrimitiveScope):
        """実registered operationのCOUNT/版/Sからreceiptを発行する。"""
        self._live()
        if type(scope) is not PrimitiveScope:
            raise PrimitiveReadError
        result = self._handle.run(
            OpenPrimitiveSnapshotToken(
                scope.game_id, scope.player_id, scope.model_sha256
            )
        )
        if len(result.rows) != 1 or len(result.rows[0]) != 8:
            raise PrimitiveReadError
        return PrimitiveSnapshot(
            _owner=self, _key=self._key, scope=scope, row=result.rows[0]
        )

    def read_page(self, receipt, *, cursor=None, page_size=500):
        """同receiptのwindow後を有限取得し、アプリで再集計しない。"""
        self._live()
        if type(receipt) is not PrimitiveSnapshot or receipt._owner is not self:
            raise PrimitiveReadError
        if type(page_size) is not int or not 1 <= page_size <= 500:
            raise PrimitiveReadError
        if cursor is not None and (
            type(cursor) is not PrimitiveCursor or cursor._binding is not receipt
        ):
            raise PrimitiveReadError
        scope = receipt.scope
        result = self._handle.run(
            ReadPrimitivePageToken(
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
        )
        return _decode_page(
            result.rows, cursor, page_size, self._maximum_integer_chars, binding=receipt
        )

    def pages(self, receipt, *, page_size=500):
        """同DB COUNTに一致する有限pageを逐次返し、全件list化しない。"""
        self._live()
        if type(receipt) is not PrimitiveSnapshot or receipt._owner is not self:
            raise PrimitiveReadError
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
