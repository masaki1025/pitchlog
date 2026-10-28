"""初球記録後の全履歴を上限2行で読む未登録宣言。復元成功は判定しない。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, cast
from uuid import UUID

from sqlalchemy import Integer, Table, Uuid, bindparam, select

from pitchlog.db.game_state.models import PlayRow
from pitchlog.db.sync_protocol.models import EventSlot, OperationEvent
from pitchlog.repositories.operation_registration import (
    OperationRegistration,
    PreparedOperation,
)
from pitchlog.repositories.tokens import TenantOperationToken


@dataclass(frozen=True, slots=True, repr=False)
class _RecordedReadToken(TenantOperationToken):
    """元gameだけを受け、tenantと上限は実行器/宣言から供給する。"""

    game_id: UUID
    _capability: ClassVar[str]

    def __post_init__(self) -> None:
        """UUID文字列やbool等の暗黙変換を拒否する。"""
        if type(self.game_id) is not UUID:
            raise ValueError("記録後readにはUUID実値が必要です")

    @property
    def capability_id(self) -> str:
        """既read能力の識別だけを返し、実行許可を生成しない。"""
        return self._capability


@dataclass(frozen=True, slots=True, repr=False)
class RecordedEventRowsReadToken(_RecordedReadToken):
    """置換/退役/NULL位置も隠さず原イベントを最大2行読む候補。"""

    _capability = "CAP:operation_events:read"


@dataclass(frozen=True, slots=True, repr=False)
class RecordedEventSlotsReadToken(_RecordedReadToken):
    """旧世代を隠さず受入スロットを最大2行読む候補。"""

    _capability = "CAP:event_slots:read"


@dataclass(frozen=True, slots=True, repr=False)
class RecordedPlayRowsReadToken(_RecordedReadToken):
    """hidden/import/legacyも隠さず物理投影を最大2行読む候補。"""

    _capability = "CAP:play_rows:read"


_EVENTS = cast(Table, OperationEvent.__table__)
_SLOTS = cast(Table, EventSlot.__table__)
_PLAYS = cast(Table, PlayRow.__table__)
RECORDED_EVENT_COLUMNS = tuple(_EVENTS.c.keys())
RECORDED_SLOT_COLUMNS = tuple(_SLOTS.c.keys())
RECORDED_PLAY_ROW_COLUMNS = tuple(_PLAYS.c.keys())


def _registration(
    token_type: type[_RecordedReadToken], table: Table, order: tuple[str, ...]
) -> OperationRegistration:
    """固定表の全列/tenant/game等値/順序/上限だけを宣言する。"""
    statement = (
        select(*table.c)
        .where(table.c.tenant_id == bindparam("tenant_id", type_=Uuid(as_uuid=True)))
        .where(table.c.game_id == bindparam("game_id", type_=Uuid(as_uuid=True)))
        .order_by(*(table.c[key].asc().nulls_last() for key in order))
        .limit(bindparam("limit", type_=Integer))
    )

    def prepare(operation: TenantOperationToken) -> PreparedOperation:
        """派生型や別宣言を拒否し、元UUIDと固定上限だけを返す。"""
        if type(operation) is not token_type:
            raise ValueError("記録後readの登録候補と実型が不一致です")
        operation.__post_init__()
        return statement, {"game_id": operation.game_id, "limit": 2}

    return OperationRegistration(
        token_type,
        token_type._capability,
        statement,
        table.c.tenant_id,
        prepare,
        required_limit_parameter="limit",
        required_limit_max=2,
    )


# runtime registry/contract/CAP catalogは変更しない。R3の正式受理前は全型未登録。
_UNREGISTERED_DECLARATIONS = (
    _registration(
        RecordedEventRowsReadToken, _EVENTS, ("generation", "d1", "d2", "id")
    ),
    _registration(RecordedEventSlotsReadToken, _SLOTS, ("generation", "d1")),
    _registration(RecordedPlayRowsReadToken, _PLAYS, ("play_number", "id")),
)
