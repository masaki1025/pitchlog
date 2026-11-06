"""CSV読取元を有限メモリの私有ディスクへ退避する。入力をコードとして復元しない。"""

from __future__ import annotations

import json
import math
import sqlite3
import tempfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal
from typing import Any, overload
from uuid import UUID

_CURRENT: ContextVar[ExportRowStore | None] = ContextVar(
    "play_export_row_store", default=None
)


def _encode(value: Any, depth: int = 0) -> list[Any]:
    """JSON内の同形タグを混同しないよう全ノードを型付きで写す。"""
    if depth > 64:
        raise ValueError("CSV読取元の深さが上限を超えました")
    if value is None or type(value) in (str, int, bool):
        return ["scalar", value]
    if type(value) is float and math.isfinite(value):
        return ["scalar", value]
    if type(value) is UUID:
        return ["uuid", str(value)]
    if type(value) is datetime:
        return ["datetime", value.isoformat()]
    if type(value) is date:
        return ["date", value.isoformat()]
    if type(value) is Decimal and value.is_finite():
        return ["decimal", str(value)]
    if type(value) in (list, tuple):
        return [
            "tuple" if type(value) is tuple else "list",
            [_encode(item, depth + 1) for item in value],
        ]
    if type(value) is dict and all(type(key) is str for key in value):
        return [
            "dict",
            [[key, _encode(item, depth + 1)] for key, item in value.items()],
        ]
    raise ValueError("CSV読取元の保存型が不正です")


def _decode(value: list[Any]) -> Any:
    """自分で書いた有限タグだけを値へ戻す。pickle/evalは使用しない。"""
    kind, data = value
    if kind == "scalar":
        return data
    if kind == "uuid":
        return UUID(data)
    if kind == "datetime":
        return datetime.fromisoformat(data)
    if kind == "date":
        return date.fromisoformat(data)
    if kind == "decimal":
        return Decimal(data)
    if kind in ("list", "tuple"):
        decoded = [_decode(item) for item in data]
        return tuple(decoded) if kind == "tuple" else decoded
    if kind == "dict":
        return {key: _decode(item) for key, item in data}
    raise ValueError("CSV読取元の保存タグが不正です")


class ExportRowStore:
    """同一要求限定のSQLite退避。全出口でcontextが削除する。"""

    def __init__(self, *, max_bytes: int = 268_435_456, max_row_bytes: int = 4_194_304):
        """行/全体の有限上限を保持する。"""
        if (
            type(max_bytes) is not int
            or type(max_row_bytes) is not int
            or min(max_bytes, max_row_bytes) < 1
        ):
            raise ValueError("CSV退避上限が不正です")
        self.max_bytes, self.max_row_bytes = max_bytes, max_row_bytes
        self.bytes = 0
        self.counter = 0
        self.directory = tempfile.TemporaryDirectory(prefix="pitchlog-export-")
        try:
            self.db = sqlite3.connect(self.directory.name + "/rows.sqlite")
            self.db.execute("PRAGMA cache_size=-2048")
            self.db.execute("PRAGMA mmap_size=0")
            self.db.execute("PRAGMA temp_store=FILE")
            self.db.execute("PRAGMA max_page_count=262144")
            self.db.execute(
                "CREATE TABLE rows (collection INTEGER, n INTEGER, row_id TEXT, "
                "play_id TEXT, data BLOB, PRIMARY KEY(collection,n))"
            )
            self.db.execute(
                "CREATE TABLE keys (collection INTEGER, data BLOB, "
                "PRIMARY KEY(collection,data))"
            )
            self.db.execute("CREATE INDEX row_lookup ON rows(collection,row_id)")
            self.db.execute("CREATE INDEX play_lookup ON rows(collection,play_id)")
        except BaseException:
            try:
                if hasattr(self, "db"):
                    self.db.close()
            finally:
                self.directory.cleanup()
            raise

    def __enter__(self) -> ExportRowStore:
        """私有ディスクの寿命を要求へ束縛する。"""
        return self

    def __exit__(self, *_args: Any) -> None:
        """成功/失敗の双方でDBとディレクトリを閉じる。"""
        try:
            self.db.close()
        finally:
            self.directory.cleanup()

    @contextmanager
    def capture(self) -> Iterator[None]:
        """現在thread/context内のrepository読取だけを退避へ切替える。"""
        token = _CURRENT.set(self)
        try:
            yield
        finally:
            _CURRENT.reset(token)

    def rows(self, source: Iterable[dict[str, Any]] = ()) -> DiskRows:
        """新しい順序付き集合を発行し一行ずつ写す。"""
        self.counter += 1
        rows = DiskRows(self, self.counter)
        rows.extend(source)
        return rows

    def keys(self) -> DiskKeys:
        """参照IDの重複排除も全量RAMへ置かずディスクで行う。"""
        self.counter += 1
        return DiskKeys(self, self.counter)


class DiskKeys:
    """参照先ID/語彙keyの私有ディスク集合。"""

    def __init__(self, store: ExportRowStore, collection: int):
        """私有store/番号を保持する。"""
        self.store, self.collection = store, collection

    def add(self, value: UUID | str) -> None:
        """UUID/文字列だけを重複排除して追加する。"""
        if type(value) not in (UUID, str):
            raise ValueError("CSV参照キーが不正です")
        payload = json.dumps(_encode(value), ensure_ascii=False).encode()
        if (
            len(payload) > self.store.max_row_bytes
            or self.store.bytes + len(payload) > self.store.max_bytes
        ):
            raise ValueError("CSV退避容量の上限を超えました")
        cursor = self.store.db.execute(
            "INSERT OR IGNORE INTO keys VALUES(?,?)", (self.collection, payload)
        )
        if cursor.rowcount:
            self.store.bytes += len(payload)

    def __iter__(self) -> Iterator[Any]:
        """キーを一つずつ固定順で読む。"""
        cursor = self.store.db.execute(
            "SELECT data FROM keys WHERE collection=? ORDER BY data", (self.collection,)
        )
        try:
            for (payload,) in cursor:
                yield _decode(json.loads(payload))
        finally:
            cursor.close()


class DiskRows(Sequence[dict[str, Any]]):
    """原本行はディスク、iteration/lookupは各一行だけ復元する。"""

    def __init__(self, store: ExportRowStore, collection: int):
        """私有storeと集合番号を保持する。"""
        self.store, self.collection, self._size = store, collection, 0

    def extend(self, source: Iterable[dict[str, Any]]) -> None:
        """有限行/全体上限を各INSERTより先に検査する。"""
        for row in source:
            payload = json.dumps(
                _encode(row), ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ).encode()
            if (
                len(payload) > self.store.max_row_bytes
                or self.store.bytes + len(payload) > self.store.max_bytes
                or self._size >= 1_000_000
            ):
                raise ValueError("CSV退避容量の上限を超えました")
            self.store.db.execute(
                "INSERT INTO rows VALUES(?,?,?,?,?)",
                (
                    self.collection,
                    self._size,
                    str(row["id"]) if "id" in row else None,
                    str(row["play_row_id"]) if "play_row_id" in row else None,
                    payload,
                ),
            )
            self.store.bytes += len(payload)
            self._size += 1

    def __len__(self) -> int:
        """全行を読まず件数を返す。"""
        return self._size

    def __iter__(self) -> Iterator[dict[str, Any]]:
        """SQLiteの有限cacheを使い一行ずつ復元する。"""
        cursor = self.store.db.execute(
            "SELECT data FROM rows WHERE collection=? ORDER BY n", (self.collection,)
        )
        try:
            for (payload,) in cursor:
                yield _decode(json.loads(payload))
        finally:
            cursor.close()

    @overload
    def __getitem__(self, index: int) -> dict[str, Any]: ...
    @overload
    def __getitem__(self, index: slice) -> Sequence[dict[str, Any]]: ...
    def __getitem__(
        self, index: int | slice
    ) -> dict[str, Any] | Sequence[dict[str, Any]]:
        """位置照合だけを許可し、sliceの全量化を禁止する。"""
        if isinstance(index, slice):
            start, stop, step = index.indices(self._size)
            if len(range(start, stop, step)) > 500:
                raise ValueError("CSV退避のslice上限を超えました")
            return tuple(self[i] for i in range(start, stop, step))
        actual = index + self._size if index < 0 else index
        if actual < 0 or actual >= self._size:
            raise IndexError(index)
        row = self.store.db.execute(
            "SELECT data FROM rows WHERE collection=? AND n=?",
            (self.collection, actual),
        ).fetchone()
        if row is None:
            raise IndexError(index)
        return _decode(json.loads(row[0]))

    def index_by(self, field: str) -> Mapping[UUID, dict[str, Any]]:
        """原本IDをディスク索引へ束縛する。"""
        return _DiskIndex(self, field)


class _DiskIndex(Mapping[UUID, dict[str, Any]]):
    def __init__(self, rows: DiskRows, field: str):
        if field not in ("id", "play_row_id"):
            raise ValueError("CSV索引の対象が不正です")
        self.rows = rows
        self.column = "row_id" if field == "id" else "play_id"

    def __len__(self) -> int:
        return self.rows.store.db.execute(
            f"SELECT COUNT(DISTINCT {self.column}) FROM rows WHERE collection=?",
            (self.rows.collection,),
        ).fetchone()[0]

    def __iter__(self) -> Iterator[UUID]:
        cursor = self.rows.store.db.execute(
            f"SELECT DISTINCT {self.column} FROM rows "
            f"WHERE collection=? ORDER BY {self.column}",
            (self.rows.collection,),
        )
        try:
            for (key,) in cursor:
                if key is not None:
                    yield UUID(key)
        finally:
            cursor.close()

    def __getitem__(self, key: UUID) -> dict[str, Any]:
        row = self.rows.store.db.execute(
            f"SELECT data FROM rows WHERE collection=? AND {self.column}=? "
            "ORDER BY n DESC LIMIT 1",
            (self.rows.collection, str(key)),
        ).fetchone()
        if row is None:
            raise KeyError(key)
        return _decode(json.loads(row[0]))


def current_row_store() -> ExportRowStore | None:
    """同一contextの私有storeだけを返す。"""
    return _CURRENT.get()
