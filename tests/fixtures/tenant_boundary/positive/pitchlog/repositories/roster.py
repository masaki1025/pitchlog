"""選手と対戦相手の文の組み立てに限る許可シンボルの正例。"""

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

_PLAYERS = Table("players", MetaData(), Column("id", Integer))
_TEAM_RECORDS = Table("team_records", MetaData(), Column("id", Integer))


class PlayerReadToken:
    """選手の読み取り操作を表す。"""


class PlayerUpdateToken:
    """選手の更新操作を表す。"""


class TeamRecordReadToken:
    """対戦相手の読み取り操作を表す。"""


type _RosterBuilderOperation = (
    PlayerReadToken | PlayerUpdateToken | TeamRecordReadToken | None
)


def _build_roster_statement(
    kind: str,
    operation: _RosterBuilderOperation,
) -> Union[Select, Insert, Update]:
    """文の組み立てだけを許可し、実行は行わない。"""
    if kind == "player_read":
        if operation is not None and not isinstance(operation, PlayerReadToken):
            raise ValueError("player_read には PlayerReadToken が必要")
        return select(_PLAYERS.c.id)
    if kind == "player_create":
        if operation is not None:
            raise ValueError("player_create には operation を渡せない")
        return insert(_PLAYERS)
    if kind == "player_update":
        if operation is not None and not isinstance(operation, PlayerUpdateToken):
            raise ValueError("player_update には PlayerUpdateToken が必要")
        return update(_PLAYERS)
    if kind == "team_read":
        if operation is not None and not isinstance(operation, TeamRecordReadToken):
            raise ValueError("team_read には TeamRecordReadToken が必要")
        return select(_TEAM_RECORDS.c.id)
    if kind == "team_create":
        if operation is not None:
            raise ValueError("team_create には operation を渡せない")
        return insert(_TEAM_RECORDS)
    if kind == "team_update":
        if operation is not None:
            raise ValueError("team_update には operation を渡せない")
        return update(_TEAM_RECORDS)
    raise ValueError(f"未知の roster 文: {kind}")
