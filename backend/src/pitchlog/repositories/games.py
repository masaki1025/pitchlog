"""preparing 試合の tenant 限定 read operation 候補を定義する。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import DateTime, Integer, Table, Uuid, and_, bindparam, or_, select
from sqlalchemy.sql.selectable import Select

from pitchlog.api.schemas.games import (
    PREPARING_GAME_PAGE_SIZE_MAX,
    decode_preparing_game_cursor,
)
from pitchlog.db.game_state.models import Game
from pitchlog.repositories.operation_registration import (
    OperationRegistration,
    PreparedOperation,
    RequiredBinding,
)
from pitchlog.repositories.tokens import TenantOperationToken

_GAMES = cast(Table, Game.__table__)
_READ_COLUMNS = (
    _GAMES.c.id,
    _GAMES.c.scheduled_at,
    _GAMES.c.game_type_key,
    _GAMES.c.tournament_key,
    _GAMES.c.away_team_record_id,
    _GAMES.c.home_team_record_id,
    _GAMES.c.plate_umpire,
    _GAMES.c.section_label,
    _GAMES.c.week_label,
    _GAMES.c.day_label,
    _GAMES.c.game_number_label,
    _GAMES.c.status,
    _GAMES.c.applied_rules,
)


@dataclass(frozen=True, slots=True)
class PreparingGameListToken(TenantOperationToken):
    """認証済み tenant の preparing 試合だけを一覧する未登録 token。"""

    limit: int = 20
    cursor: str | None = None

    def __post_init__(self) -> None:
        """件数とカーソルの型・内容を実行前に検査する。"""
        if (
            type(self.limit) is not int
            or not 1 <= self.limit <= PREPARING_GAME_PAGE_SIZE_MAX
        ):
            raise ValueError("limit は 1〜100 が必要")
        if self.cursor is not None:
            decode_preparing_game_cursor(self.cursor)

    @property
    def capability_id(self) -> str:
        """既存の試合 read capability を返す。"""
        return "CAP:games:read"


@dataclass(frozen=True, slots=True)
class PreparingGameDetailToken(TenantOperationToken):
    """認証済み tenant の可視な preparing 試合を1件読む未登録 token。"""

    game_id: UUID

    def __post_init__(self) -> None:
        """試合 ID を厳密な UUID に限定する。"""
        if type(self.game_id) is not UUID:
            raise ValueError("game_id は UUID が必要")

    @property
    def capability_id(self) -> str:
        """既存の試合 read capability を返す。"""
        return "CAP:games:read"


def _preparing_game_list_statement(
    cursor_position: tuple[datetime, UUID] | None = None,
) -> Select[Any]:
    """可視な preparing 試合を索引順の keyset で最大 limit 件読む。"""
    statement = (
        select(*_READ_COLUMNS)
        .where(_GAMES.c.tenant_id == bindparam("tenant_id"))
        .where(_GAMES.c.status == bindparam("status"))
        .where(_GAMES.c.trashed_at.is_(None))
        .where(_GAMES.c.hidden_at.is_(None))
    )
    if cursor_position is not None:
        statement = statement.where(
            or_(
                _GAMES.c.scheduled_at
                < bindparam("cursor_scheduled_at", type_=DateTime(timezone=True)),
                and_(
                    _GAMES.c.scheduled_at
                    == bindparam("cursor_scheduled_at", type_=DateTime(timezone=True)),
                    _GAMES.c.id < bindparam("cursor_id", type_=Uuid(as_uuid=True)),
                ),
            )
        )
    return statement.order_by(_GAMES.c.scheduled_at.desc(), _GAMES.c.id.desc()).limit(
        bindparam("limit", type_=Integer)
    )


def _preparing_game_detail_statement() -> Select[Any]:
    """同じ可視性条件で ID を指定した1試合だけを読む。"""
    return (
        select(*_READ_COLUMNS)
        .where(_GAMES.c.tenant_id == bindparam("tenant_id"))
        .where(_GAMES.c.status == bindparam("status"))
        .where(_GAMES.c.trashed_at.is_(None))
        .where(_GAMES.c.hidden_at.is_(None))
        .where(_GAMES.c.id == bindparam("game_id", type_=Uuid(as_uuid=True)))
        .limit(bindparam("limit", type_=Integer))
    )


def _prepare_preparing_game_list(operation: TenantOperationToken) -> PreparedOperation:
    """一覧 token を1文と tenant 以外の束縛値へ変換する。"""
    if type(operation) is not PreparingGameListToken:
        raise ValueError("一覧 token が必要")
    token = operation
    position = (
        decode_preparing_game_cursor(token.cursor) if token.cursor is not None else None
    )
    parameters: dict[str, object] = {"status": "preparing", "limit": token.limit + 1}
    if position is not None:
        parameters["cursor_scheduled_at"], parameters["cursor_id"] = position
    return _preparing_game_list_statement(position), parameters


def _prepare_preparing_game_detail(
    operation: TenantOperationToken,
) -> PreparedOperation:
    """詳細 token を1件だけの文と tenant 以外の束縛値へ変換する。"""
    if type(operation) is not PreparingGameDetailToken:
        raise ValueError("詳細 token が必要")
    token = operation
    return _preparing_game_detail_statement(), {
        "status": "preparing",
        "game_id": token.game_id,
        "limit": 1,
    }


# Step 3 では候補に留める。製品 registry と実行器には登録しない。
PREPARING_GAME_READ_OPERATIONS: tuple[OperationRegistration, ...] = (
    OperationRegistration(
        PreparingGameListToken,
        "CAP:games:read",
        _preparing_game_list_statement(),
        _GAMES.c.tenant_id,
        _prepare_preparing_game_list,
        required_bindings=(RequiredBinding(_GAMES.c.status, "status", "preparing"),),
        required_limit_parameter="limit",
        required_limit_max=PREPARING_GAME_PAGE_SIZE_MAX + 1,
    ),
    OperationRegistration(
        PreparingGameDetailToken,
        "CAP:games:read",
        _preparing_game_detail_statement(),
        _GAMES.c.tenant_id,
        _prepare_preparing_game_detail,
        required_bindings=(RequiredBinding(_GAMES.c.status, "status", "preparing"),),
        required_limit_parameter="limit",
        required_limit_max=1,
    ),
)
