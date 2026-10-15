"""同期の SQL 構築窓口だけを許可する正例。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Table, insert, select, update  # ty: ignore[unresolved-import]
from sqlalchemy.sql.dml import Insert, Update  # ty: ignore[unresolved-import]
from sqlalchemy.sql.selectable import Select  # ty: ignore[unresolved-import]


def _build_sync_statement(
    kind: str,
    table: Table,
    columns: tuple[str, ...] = (),
    keys: tuple[str, ...] = (),
    values: tuple[str, ...] = (),
) -> Select[Any] | Insert | Update:
    """固定した表の read・insert・update だけを作る。"""
    del columns, keys, values
    if kind == "read":
        return select(table)
    if kind == "insert":
        return insert(table)
    if kind == "update":
        return update(table)
    raise ValueError(kind)
