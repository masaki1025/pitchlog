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
from pitchlog.db.tenant_isolation.models import Player, TeamRecord
from pitchlog.repositories.operation_registration import (
    OperationPreflight,
    OperationRegistration,
    PreparedOperation,
    PrimaryKeyBinding,
    RequiredBinding,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken

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
_PLAYERS = cast(Table, Player.__table__)
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
class _ActiveLineupPlayerLockToken(TenantOperationToken):
    """自チームの現役選手 1 行を保存終了までロックする。"""

    team_record_id: UUID
    player_id: UUID

    @property
    def capability_id(self) -> str:
        """選手読み取り capability を返す。"""
        return "CAP:players:read"


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
    team_record_id: UUID
    lineup_json: str

    @property
    def capability_id(self) -> str:
        """記憶の更新 capability を返す。"""
        return "CAP:lineup_memories:update"


def _build_lineup_memory_statement(kind: str) -> Union[Select, Insert, Update]:
    """登録済みの単一表操作に限って文を組み立てる。"""
    if kind == "lock":
        return (
            select(_TEAMS.c.id)
            .where(_TEAMS.c.tenant_id == bindparam("tenant_id"))
            .where(_TEAMS.c.id == bindparam("team_record_id", type_=Uuid(as_uuid=True)))
            .where(_TEAMS.c.kind == bindparam("kind"))
            .where(_TEAMS.c.hidden_at.is_(None))
            .with_for_update()
        )
    if kind == "player_lock":
        return (
            select(_PLAYERS.c.id)
            .where(_PLAYERS.c.tenant_id == bindparam("tenant_id"))
            .where(_PLAYERS.c.id == bindparam("player_id", type_=Uuid(as_uuid=True)))
            .where(
                _PLAYERS.c.team_record_id
                == bindparam("team_record_id", type_=Uuid(as_uuid=True))
            )
            .where(_PLAYERS.c.roster_status_key == bindparam("roster_status_key"))
            .where(_PLAYERS.c.hidden_at.is_(None))
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
            .where(
                _MEMORIES.c.team_record_id
                == bindparam("where_team_record_id", type_=Uuid(as_uuid=True))
            )
            .where(_MEMORIES.c.migration_preserved_only.is_(False))
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


def _prepare_player_lock(token: TenantOperationToken) -> PreparedOperation:
    """現役選手 1 行の ID・チーム・固定区分を束縛する。"""
    operation = cast(_ActiveLineupPlayerLockToken, token)
    return _build_lineup_memory_statement("player_lock"), {
        "player_id": operation.player_id,
        "team_record_id": operation.team_record_id,
        "roster_status_key": "active",
    }


def _fixed_uuid(value: UUID) -> UUID:
    """呼び出し元の UUID 参照から独立した束縛値を作る。"""
    if type(value) is not UUID:
        raise ValueError("識別子は UUID が必要")
    return UUID(int=value.int)


def _prepare_read(token: TenantOperationToken) -> PreparedOperation:
    """読み取り対象チームだけを束縛する。"""
    operation = cast(LineupMemoryReadToken, token)
    return _build_lineup_memory_statement("read"), {
        "team_record_id": _fixed_uuid(operation.team_record_id)
    }


def _prepare_insert(token: TenantOperationToken) -> PreparedOperation:
    """不変 token の JSON 文字列を実行直前に新しい値へ復元する。"""
    operation = cast(_LineupMemoryInsertToken, token)
    return _build_lineup_memory_statement("insert"), {
        "id": _fixed_uuid(operation.id),
        "team_record_id": _fixed_uuid(operation.team_record_id),
        "lineup": _decode_lineup_json(operation.lineup_json)[0],
    }


def _prepare_update(token: TenantOperationToken) -> PreparedOperation:
    """既存記憶 ID と新しい JSON を束縛する。"""
    operation = cast(_LineupMemoryUpdateToken, token)
    return _build_lineup_memory_statement("update"), {
        "where_id": _fixed_uuid(operation.id),
        "where_team_record_id": _fixed_uuid(operation.team_record_id),
        "lineup": _decode_lineup_json(operation.lineup_json)[0],
    }


def _normalize_lineup(
    lineup: tuple[Mapping[str, object], ...],
) -> tuple[list[dict[str, object]], tuple[UUID, ...]]:
    """確定オーダーの識別項目を検査し、選手 ID を正規化する。"""
    if not lineup:
        raise ValueError("確定済みオーダーが必要")
    payload: list[dict[str, object]] = []
    seen_players: set[UUID] = set()
    for entry in lineup:
        if (
            not isinstance(entry, Mapping)
            or not {"player_id", "batting_order", "fielding_position"} <= entry.keys()
        ):
            raise ValueError("確定オーダーの識別項目が欠けている")
        if type(entry["player_id"]) is not str:
            raise ValueError("選手 ID は UUID 文字列が必要")
        try:
            player_id = UUID(entry["player_id"])
        except (TypeError, ValueError, AttributeError) as error:
            raise ValueError("選手 ID が不正") from error
        if player_id in seen_players:
            raise ValueError("確定オーダーの選手 ID が重複している")
        seen_players.add(player_id)
        payload.append(
            {
                "player_id": str(player_id),
                "batting_order": entry["batting_order"],
                "fielding_position": entry["fielding_position"],
            }
        )
    return payload, tuple(sorted(seen_players))


def _decode_lineup_json(
    lineup_json: str,
) -> tuple[list[dict[str, object]], tuple[UUID, ...]]:
    """直接 token の JSON も保存用の正規形へ変換する。"""
    if type(lineup_json) is not str:
        raise ValueError("確定オーダーは不変な JSON 文字列が必要")
    try:
        decoded = json.loads(lineup_json)
    except (TypeError, ValueError) as error:
        raise ValueError("確定オーダーは JSON 値が必要") from error
    if not isinstance(decoded, list):
        raise ValueError("確定オーダーは配列が必要")
    return _normalize_lineup(tuple(decoded))


def _preflight_lineup_memory(
    token: TenantOperationToken, parameters: dict[str, object]
) -> OperationPreflight:
    """保存 SQL と同じ束縛値で自チームと現役名簿を照合する。"""
    team_value = parameters[
        "where_team_record_id"
        if isinstance(token, _LineupMemoryUpdateToken)
        else "team_record_id"
    ]
    if type(team_value) is not UUID:
        raise ValueError("自チーム ID は UUID が必要")
    team_record_id = team_value
    checks: list[TenantOperationToken] = [_SelfTeamLockToken(team_record_id)]
    if not isinstance(token, LineupMemoryReadToken):
        lineup = parameters["lineup"]
        if type(lineup) is not list:
            raise ValueError("確定オーダーは配列が必要")
        _, player_ids = _normalize_lineup(
            cast(tuple[Mapping[str, object], ...], tuple(lineup))
        )
        checks.extend(
            _ActiveLineupPlayerLockToken(team_record_id, player_id)
            for player_id in player_ids
        )

    def validate(results: tuple[TenantOperationResult, ...]) -> None:
        """同一トランザクションで取得した検証結果を拒否側へ閉じる。"""
        if any(not result.rows for result in results):
            raise LineupMemoryUnavailable("自チームまたは現役選手が利用できない")

    return OperationPreflight(tuple(checks), validate)


LINEUP_MEMORY_OPERATIONS: tuple[OperationRegistration, ...] = (
    OperationRegistration(
        _SelfTeamLockToken,
        "CAP:team_records:read",
        _build_lineup_memory_statement("lock"),
        _TEAMS.c.tenant_id,
        _prepare_lock,
        required_bindings=(RequiredBinding(_TEAMS.c.kind, "kind", "self"),),
        primary_key_bindings=(
            PrimaryKeyBinding(_TEAMS.c.tenant_id, "tenant_id"),
            PrimaryKeyBinding(_TEAMS.c.id, "team_record_id"),
        ),
        for_update=True,
        use_capability_lock_shape=True,
    ),
    OperationRegistration(
        _ActiveLineupPlayerLockToken,
        "CAP:players:read",
        _build_lineup_memory_statement("player_lock"),
        _PLAYERS.c.tenant_id,
        _prepare_player_lock,
        required_bindings=(
            RequiredBinding(
                _PLAYERS.c.roster_status_key, "roster_status_key", "active"
            ),
        ),
        primary_key_bindings=(
            PrimaryKeyBinding(_PLAYERS.c.tenant_id, "tenant_id"),
            PrimaryKeyBinding(_PLAYERS.c.id, "player_id"),
        ),
        for_update=True,
        use_capability_lock_shape=True,
    ),
    OperationRegistration(
        LineupMemoryReadToken,
        "CAP:lineup_memories:read",
        _build_lineup_memory_statement("read"),
        _MEMORIES.c.tenant_id,
        _prepare_read,
        preflight=_preflight_lineup_memory,
    ),
    OperationRegistration(
        _LineupMemoryInsertToken,
        "CAP:lineup_memories:insert",
        _build_lineup_memory_statement("insert"),
        _MEMORIES.c.tenant_id,
        _prepare_insert,
        preflight=_preflight_lineup_memory,
    ),
    OperationRegistration(
        _LineupMemoryUpdateToken,
        "CAP:lineup_memories:update",
        _build_lineup_memory_statement("update"),
        _MEMORIES.c.tenant_id,
        _prepare_update,
        allowed_update_columns=frozenset({"lineup"}),
        preflight=_preflight_lineup_memory,
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
    payload, _ = _normalize_lineup(lineup)

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
            _LineupMemoryUpdateToken(
                cast(UUID, current[0][0]), team_record_id, lineup_json
            )
        )
    if result.rows == ((0,),):
        raise LineupMemoryUnavailable("スタメン記憶を保存できない")
    verified = scope.run(LineupMemoryReadToken(team_record_id)).rows
    expected = tuple(MappingProxyType(entry) for entry in payload)
    if len(verified) != 1 or verified[0][1] != expected:
        raise LineupMemoryUnavailable("スタメン記憶の保存結果が一致しない")
