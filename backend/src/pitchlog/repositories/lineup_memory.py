"""自チームの直近スタメンを同一テナントの確定トランザクションで記憶する。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Union, cast
from uuid import UUID, uuid4

from sqlalchemy import Table, Uuid, bindparam, insert, select, update
from sqlalchemy.sql.dml import Insert, Update
from sqlalchemy.sql.selectable import Select

from pitchlog.db.game_state.models import LineupMemory
from pitchlog.db.tenant_isolation.models import TeamRecord
from pitchlog.repositories.operation_registration import (
    OperationRegistration,
    PreparedOperation,
    RequiredBinding,
)
from pitchlog.repositories.roster import PlayerReadToken
from pitchlog.repositories.tokens import TenantOperationToken

if TYPE_CHECKING:
    from pitchlog.repositories.transaction import _TenantTransaction

__all__ = (
    "LineupMemoryUnavailable",
    "LineupMemoryReadToken",
    "save_lineup_memory",
)


class LineupMemoryUnavailable(ValueError):
    """対象チームまたは確定オーダーの選手が利用できないことを表す。"""


_TEAMS = cast(Table, TeamRecord.__table__)
_MEMORIES = cast(Table, LineupMemory.__table__)


@dataclass(frozen=True, slots=True)
class _SelfTeamLockToken(TenantOperationToken):
    """自チームの対象行だけを確定までロックする。"""

    team_record_id: UUID

    @property
    def capability_id(self) -> str:
        """チーム読み取り capability を返す。"""
        return "CAP:team_records:read"


@dataclass(frozen=True, slots=True)
class LineupMemoryReadToken(TenantOperationToken):
    """対象チームの退役していない記憶を 1 行読む。"""

    team_record_id: UUID

    @property
    def capability_id(self) -> str:
        """記憶の読み取り capability を返す。"""
        return "CAP:lineup_memories:read"


@dataclass(frozen=True, slots=True)
class _LineupMemoryInsertToken(TenantOperationToken):
    """確定済みオーダーの初回記憶を挿入する。"""

    id: UUID
    team_record_id: UUID
    lineup_json: str

    @property
    def capability_id(self) -> str:
        """記憶の追加 capability を返す。"""
        return "CAP:lineup_memories:insert"


@dataclass(frozen=True, slots=True)
class _LineupMemoryUpdateToken(TenantOperationToken):
    """既存の有効な記憶のオーダーだけを更新する。"""

    id: UUID
    lineup_json: str

    @property
    def capability_id(self) -> str:
        """記憶の更新 capability を返す。"""
        return "CAP:lineup_memories:update"


def _build_lineup_memory_statement(kind: str) -> Union[Select, Insert, Update]:
    """登録済みの4操作に限り、単一表の文を組み立てる。"""
    if kind == "lock":
        return (
            select(_TEAMS.c.id)
            .where(_TEAMS.c.tenant_id == bindparam("tenant_id"))
            .where(_TEAMS.c.id == bindparam("team_record_id", type_=Uuid(as_uuid=True)))
            .where(_TEAMS.c.kind == bindparam("kind"))
            .where(_TEAMS.c.hidden_at.is_(None))
            .with_for_update()
        )
    if kind == "read":
        return (
            select(
                _MEMORIES.c.id,
                _MEMORIES.c.lineup,
                _MEMORIES.c.migration_preserved_only,
            )
            .where(_MEMORIES.c.tenant_id == bindparam("tenant_id"))
            .where(
                _MEMORIES.c.team_record_id
                == bindparam("team_record_id", type_=Uuid(as_uuid=True))
            )
            .where(_MEMORIES.c.retired_at.is_(None))
            .limit(1)
        )
    if kind == "insert":
        return insert(_MEMORIES).values(
            tenant_id=bindparam("tenant_id"),
            id=bindparam("id"),
            team_record_id=bindparam("team_record_id"),
            lineup=bindparam("lineup"),
        )
    if kind == "update":
        return (
            update(_MEMORIES)
            .where(_MEMORIES.c.tenant_id == bindparam("where_tenant_id"))
            .where(_MEMORIES.c.id == bindparam("where_id", type_=Uuid(as_uuid=True)))
            .where(_MEMORIES.c.retired_at.is_(None))
            .values(lineup=bindparam("lineup"))
        )
    raise ValueError(f"未知のスタメン記憶操作: {kind}")


def _prepare_lock(token: TenantOperationToken) -> PreparedOperation:
    """ロック対象と固定 self 種別を束縛する。"""
    operation = cast(_SelfTeamLockToken, token)
    return _build_lineup_memory_statement("lock"), {
        "team_record_id": operation.team_record_id,
        "kind": "self",
    }


def _prepare_read(token: TenantOperationToken) -> PreparedOperation:
    """読み取り対象チームだけを束縛する。"""
    operation = cast(LineupMemoryReadToken, token)
    return _build_lineup_memory_statement("read"), {
        "team_record_id": operation.team_record_id
    }


def _prepare_insert(token: TenantOperationToken) -> PreparedOperation:
    """不変 token の JSON 文字列を実行直前に新しい値へ復元する。"""
    operation = cast(_LineupMemoryInsertToken, token)
    return _build_lineup_memory_statement("insert"), {
        "id": operation.id,
        "team_record_id": operation.team_record_id,
        "lineup": json.loads(operation.lineup_json),
    }


def _prepare_update(token: TenantOperationToken) -> PreparedOperation:
    """既存記憶 ID と新しい JSON を束縛する。"""
    operation = cast(_LineupMemoryUpdateToken, token)
    return _build_lineup_memory_statement("update"), {
        "where_id": operation.id,
        "lineup": json.loads(operation.lineup_json),
    }


LINEUP_MEMORY_OPERATIONS: tuple[OperationRegistration, ...] = (
    OperationRegistration(
        _SelfTeamLockToken,
        "CAP:team_records:read",
        _build_lineup_memory_statement("lock"),
        _TEAMS.c.tenant_id,
        _prepare_lock,
        required_bindings=(RequiredBinding(_TEAMS.c.kind, "kind", "self"),),
    ),
    OperationRegistration(
        LineupMemoryReadToken,
        "CAP:lineup_memories:read",
        _build_lineup_memory_statement("read"),
        _MEMORIES.c.tenant_id,
        _prepare_read,
    ),
    OperationRegistration(
        _LineupMemoryInsertToken,
        "CAP:lineup_memories:insert",
        _build_lineup_memory_statement("insert"),
        _MEMORIES.c.tenant_id,
        _prepare_insert,
    ),
    OperationRegistration(
        _LineupMemoryUpdateToken,
        "CAP:lineup_memories:update",
        _build_lineup_memory_statement("update"),
        _MEMORIES.c.tenant_id,
        _prepare_update,
        allowed_update_columns=frozenset({"lineup"}),
    ),
)


def save_lineup_memory(
    scope: _TenantTransaction,
    team_record_id: UUID,
    lineup: tuple[Mapping[str, object], ...],
) -> None:
    """U-G1 の確定 scope 内で現役選手のオーダーを直近 1 件に保存する。

    Args:
        scope: 試合スタメン確定と同じテナントトランザクション。
        team_record_id: 当該テナントの自チーム ID。
        lineup: U-G1 が妥当性を確定した JSON 要素。位置値は変換しない。

    Raises:
        LineupMemoryUnavailable: 対象チームまたは現役選手が利用できない場合。
    """
    if type(team_record_id) is not UUID or type(lineup) is not tuple or not lineup:
        raise ValueError("自チーム ID と確定済みオーダーが必要")
    if not scope.run(_SelfTeamLockToken(team_record_id)).rows:
        raise LineupMemoryUnavailable("自チームが利用できない")

    payload: list[dict[str, object]] = []
    seen_players: set[UUID] = set()
    for entry in lineup:
        if (
            not isinstance(entry, Mapping)
            or not {"player_id", "batting_order", "fielding_position"} <= entry.keys()
        ):
            raise ValueError("確定オーダーの識別項目が欠けている")
        try:
            player_id = UUID(str(entry["player_id"]))
        except (TypeError, ValueError, AttributeError) as error:
            raise ValueError("選手 ID が不正") from error
        if player_id in seen_players:
            raise ValueError("確定オーダーの選手 ID が重複している")
        seen_players.add(player_id)
        player_rows = scope.run(
            PlayerReadToken(limit=1, record_id=player_id, team_record_id=team_record_id)
        ).rows
        if not player_rows or player_rows[0][6] != "active":
            raise LineupMemoryUnavailable("選手が自チームの現役名簿にいない")
        payload.append(
            {
                "player_id": str(player_id),
                "batting_order": entry["batting_order"],
                "fielding_position": entry["fielding_position"],
            }
        )

    try:
        lineup_json = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("確定オーダーは JSON 値が必要") from error
    current = scope.run(LineupMemoryReadToken(team_record_id)).rows
    if not current:
        result = scope.run(
            _LineupMemoryInsertToken(uuid4(), team_record_id, lineup_json)
        )
    else:
        if current[0][2] is not False:
            raise LineupMemoryUnavailable("移行由来の記憶は新規運用へ転用できない")
        result = scope.run(
            _LineupMemoryUpdateToken(cast(UUID, current[0][0]), lineup_json)
        )
    if result.rows == ((0,),):
        raise LineupMemoryUnavailable("スタメン記憶を保存できない")
    verified = scope.run(LineupMemoryReadToken(team_record_id)).rows
    expected = tuple(MappingProxyType(entry) for entry in payload)
    if len(verified) != 1 or verified[0][1] != expected:
        raise LineupMemoryUnavailable("スタメン記憶の保存結果が一致しない")
