"""スタメン記憶の登録済み単一表文だけを許可する正例。"""

from __future__ import annotations

from typing import Union

from sqlalchemy import (  # ty: ignore[unresolved-import]
    Column,
    Integer,
    MetaData,
    Table,
    insert,
    select,
    update,
)
from sqlalchemy.sql.dml import Insert, Update  # ty: ignore[unresolved-import]
from sqlalchemy.sql.selectable import Select  # ty: ignore[unresolved-import]

_TEAMS = Table("team_records", MetaData(), Column("id", Integer))
_MEMORIES = Table("lineup_memories", MetaData(), Column("id", Integer))


def _build_lineup_memory_statement(kind: str) -> Union[Select, Insert, Update]:
    """スタメン記憶の read・insert・update とチームロック文を作る。"""
    if kind == "lock":
        return select(_TEAMS.c.id)
    if kind == "read":
        return select(_MEMORIES.c.id)
    if kind == "insert":
        return insert(_MEMORIES)
    if kind == "update":
        return update(_MEMORIES)
    raise ValueError(kind)
