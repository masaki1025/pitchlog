"""初球前の保存原本に限る有限read操作。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, cast
from uuid import UUID

from sqlalchemy import Integer, Table, Uuid, bindparam, select

from pitchlog.db.game_state.models import GameLineup, PlayRow
from pitchlog.db.sync_protocol.models import EventSlot, OperationEvent
from pitchlog.repositories.operation_registration import (
    OperationRegistration,
    PreparedOperation,
)
from pitchlog.repositories.tokens import TenantOperationToken

LINEUP_COLUMNS = (
    "tenant_id",
    "id",
    "game_id",
    "team_record_id",
    "entries_with_uniform_number_snapshot",
)


@dataclass(frozen=True, slots=True)
class _StartedReadToken(TenantOperationToken):
    """試合だけを受け取り、tenantは既executorに束縛させる。"""

    game_id: UUID
    _capability: ClassVar[str]

    def __post_init__(self) -> None:
        """UUIDの暗黙変換やtenant入力を受け付けない。"""
        if type(self.game_id) is not UUID:
            raise ValueError("started readにはUUIDが必要")

    @property
    def capability_id(self) -> str:
        """既存の単一read能力だけを返す。"""
        return self._capability


@dataclass(frozen=True, slots=True)
class StartedLineupsReadToken(_StartedReadToken):
    """両lineupと過剰一件だけを読む候補。"""

    _capability = "CAP:game_lineups:read"


@dataclass(frozen=True, slots=True)
class StartedEventSlotsExistenceToken(_StartedReadToken):
    """世代を限定せずslotの存在一件を読む候補。"""

    _capability = "CAP:event_slots:read"


@dataclass(frozen=True, slots=True)
class StartedOperationEventsExistenceToken(_StartedReadToken):
    """NULL D2や退役・置換も含むevent一件を読む候補。"""

    _capability = "CAP:operation_events:read"


@dataclass(frozen=True, slots=True)
class StartedPlayRowsExistenceToken(_StartedReadToken):
    """初期投影へ混入したplay一件を読む候補。"""

    _capability = "CAP:play_rows:read"


def _registration(
    token_type: type[_StartedReadToken],
    model: Any,
    *,
    lineups: bool = False,
) -> OperationRegistration:
    """固定表・tenant/game等値・固定上限のread候補を構築する。"""
    table = cast(Table, model.__table__)
    columns = (
        tuple(table.c[name] for name in LINEUP_COLUMNS)
        if lineups
        else (table.c.game_id,)
    )
    statement = (
        select(*columns)
        .where(table.c.tenant_id == bindparam("tenant_id", type_=Uuid(as_uuid=True)))
        .where(table.c.game_id == bindparam("game_id", type_=Uuid(as_uuid=True)))
        .limit(bindparam("limit", type_=Integer))
    )
    if lineups:
        statement = statement.order_by(table.c.team_record_id, table.c.id)
    limit = 3 if lineups else 1

    def prepare(operation: TenantOperationToken) -> PreparedOperation:
        """候補の実型と元UUIDを再検査し、任意条件を加えない。"""
        if type(operation) is not token_type:
            raise ValueError("登録されたstarted tokenの実型が必要")
        token = operation
        token.__post_init__()
        return statement, {"game_id": token.game_id, "limit": limit}

    return OperationRegistration(
        token_type,
        token_type._capability,
        statement,
        table.c.tenant_id,
        prepare,
        required_limit_parameter="limit",
        required_limit_max=limit,
    )


# 新しいCAPを作らず、既read能力と固定上限で製品実行器へ登録する。
STARTED_SNAPSHOT_OPERATIONS = (
    _registration(StartedLineupsReadToken, GameLineup, lineups=True),
    _registration(StartedEventSlotsExistenceToken, EventSlot),
    _registration(StartedOperationEventsExistenceToken, OperationEvent),
    _registration(StartedPlayRowsExistenceToken, PlayRow),
)
