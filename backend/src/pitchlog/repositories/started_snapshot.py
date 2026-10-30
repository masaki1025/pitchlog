"""同writerの空の開始済み原本から初球入力だけを構成する未登録reader。

認証・現在権利・Port登録・保存の証明は返さない。初期条件を満たさない原本を
0で補わず、配置計算は既単一artifactへ委ねる。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID

from pitchlog.db.game_state.models import Game
from pitchlog.domainrt.first_pitch import StateSnapshot
from pitchlog.domainrt.first_pitch_continuation import SavedRuleWire
from pitchlog.domainrt.initial_game_roster import (
    InitialGameRosterRequest,
    InitialRosterProjection,
    RosterEntry,
    evaluate_initial_game_roster,
)
from pitchlog.repositories.game_start import _saved_start_rule_wire
from pitchlog.repositories.roster import PlayerReadToken, player_read_statement
from pitchlog.repositories.started_snapshot_operations import (
    LINEUP_COLUMNS,
    StartedEventSlotsExistenceToken,
    StartedLineupsReadToken,
    StartedOperationEventsExistenceToken,
    StartedPlayRowsExistenceToken,
)
from pitchlog.repositories.sync_apply import _GENERATION_READ_COLUMNS
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.tokens import (
    GameLockToken,
    GameReadToken,
    RecordingGenerationLockToken,
    RecordingGenerationReadToken,
)


class StartedSnapshotUnavailable(RuntimeError):
    """入力や資格を含まない固定の非成功。"""

    def __init__(self) -> None:
        """欠損を初期値として返さない。"""
        super().__init__("開始済み初球原本を確認できません")


@dataclass(frozen=True, slots=True)
class SavedLineupEntry:
    """保存した役割と背番号を、現在の名簿値へ置換せず保持する。"""

    roster: RosterEntry
    uniform_number_snapshot: str | None


@dataclass(frozen=True, slots=True)
class SavedStartedLineup:
    """同試合の保存済みlineup原本。"""

    id: UUID
    team_id: UUID
    entries: tuple[SavedLineupEntry, ...]


@dataclass(frozen=True, slots=True)
class StartedInitialSnapshot:
    """同read内の入力値。writerや現在権利の証明として使わない。"""

    tenant_id: UUID
    game_id: UUID
    started_at: datetime
    generation: int
    confirmed_watermark: int
    applied_prefix: int
    lineups: tuple[SavedStartedLineup, SavedStartedLineup]
    saved_rules_json: str
    before: StateSnapshot
    rules: SavedRuleWire
    roster: InitialRosterProjection


def _rows(
    result: TenantOperationResult, columns: tuple[str, ...]
) -> list[dict[str, Any]]:
    """executorの不変tupleと既選択列数を厳密に照合する。"""
    if type(result) is not TenantOperationResult or type(result.rows) is not tuple:
        raise StartedSnapshotUnavailable
    if any(type(row) is not tuple or len(row) != len(columns) for row in result.rows):
        raise StartedSnapshotUnavailable
    return [dict(zip(columns, row, strict=True)) for row in result.rows]


def _one(result: TenantOperationResult, columns: tuple[str, ...]) -> dict[str, Any]:
    """欠落・重複を成功へ正規化しない。"""
    rows = _rows(result, columns)
    if len(rows) != 1:
        raise StartedSnapshotUnavailable
    return rows[0]


def _plain(value: Any) -> Any:
    """executorのJSON不変値を防御的に複製し、暗黙変換を拒否する。"""
    if type(value) is MappingProxyType:
        if any(type(key) is not str for key in value):
            raise StartedSnapshotUnavailable
        return {key: _plain(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_plain(item) for item in value]
    if value is None or type(value) in (str, int, bool):
        return value
    raise StartedSnapshotUnavailable


def _uuid(value: Any) -> UUID:
    """DBのUUID実値だけを受け取る。"""
    if type(value) is not UUID:
        raise StartedSnapshotUnavailable
    return value


def _saved_lineup(row: dict[str, Any]) -> SavedStartedLineup:
    """保存entryの全fieldを保持し、配置の適否は計算しない。"""
    source = _plain(row["entries_with_uniform_number_snapshot"])
    if type(source) is not list or not 9 <= len(source) <= 10:
        raise StartedSnapshotUnavailable
    entries = []
    for entry in source:
        if type(entry) is not dict or set(entry) != {
            "player_id",
            "batting_order",
            "fielding_position",
            "uniform_number_snapshot",
        }:
            raise StartedSnapshotUnavailable
        player = entry["player_id"]
        if type(player) is not str or str(UUID(player)) != player:
            raise StartedSnapshotUnavailable
        order = entry["batting_order"]
        if order is not None and (type(order) is not int or not 1 <= order <= 9):
            raise StartedSnapshotUnavailable
        role = entry["fielding_position"]
        if type(role) is not dict:
            raise StartedSnapshotUnavailable
        if role == {"kind": "designated-hitter"}:
            role_wire = role
        elif (
            set(role) == {"kind", "position"}
            and role["kind"] == "fielding"
            and type(role["position"]) is int
            and 1 <= role["position"] <= 9
        ):
            role_wire = {"kind": "fielding", "position": str(role["position"])}
        else:
            raise StartedSnapshotUnavailable
        uniform = entry["uniform_number_snapshot"]
        if uniform is not None and type(uniform) is not str:
            raise StartedSnapshotUnavailable
        roster = RosterEntry.model_validate(
            {
                "player_id": player,
                "batting_order": None if order is None else str(order),
                "fielding_position": role_wire,
            }
        )
        entries.append(SavedLineupEntry(roster, uniform))
    return SavedStartedLineup(
        _uuid(row["id"]), _uuid(row["team_record_id"]), tuple(entries)
    )


def _initial_before() -> StateSnapshot:
    """空原本又は唯一のnative初球の開始原典を呼出側が確認した後に使う。"""
    return StateSnapshot.model_validate(
        {
            "stateFields": {
                "state.half": "top",
                "state.count.strikes": "0",
                "state.count.balls": "0",
                "state.outs": "0",
                "state.runners": "empty",
                "state.battingOrder": "1",
                "state.tiebreakActive": False,
                "state.gameEnded": False,
                "state.inning": "1",
                "state.score": {"home": "0", "away": "0"},
            },
            "scoreboard": {
                "inningScores": {"home": "0", "away": "0"},
                "hits": "0",
                "errors": "0",
                "strikeouts": "0",
                "walks": "0",
            },
        }
    )


def read_initial_started_snapshot(
    handle: _TenantTransaction,
    game_id: UUID,
) -> StartedInitialSnapshot:
    """同handleの保存原本を照合し、初球before/rulesだけを返す。

    Args:
        handle: 既scopeが所有する生存中のwriter。別Sessionは開かない。
        game_id: 対象試合のUUID。tenantはhandleからのみ得る。

    Returns:
        初期入力値。認証・現在権利・実保存の成功ではない。

    Raises:
        StartedSnapshotUnavailable: 原本不整合、未登録操作、scope失効、計算非成功。
    """
    try:
        if type(handle) is not _TenantTransaction:
            raise StartedSnapshotUnavailable
        tenant = _uuid(getattr(handle, "_bound_tenant_id", None))
        _uuid(game_id)
        state_key = getattr(handle, "_state_key", None)
        if state_key is None:
            raise StartedSnapshotUnavailable

        def run(operation: TenantOperationToken) -> TenantOperationResult:
            """各readの前後で同じwriterキーとtenantを保持する。"""
            if handle._state_key is not state_key or handle._bound_tenant_id != tenant:
                raise StartedSnapshotUnavailable
            value = handle.run(operation)
            if handle._state_key is not state_key or handle._bound_tenant_id != tenant:
                raise StartedSnapshotUnavailable
            return value

        columns = tuple(Game.__table__.c.keys())
        locked = _one(run(GameLockToken(game_id)), columns)
        game = _one(run(GameReadToken(game_id)), columns)
        if locked != game or game["tenant_id"] != tenant or game["id"] != game_id:
            raise StartedSnapshotUnavailable
        if (
            game["status"] != "in_progress"
            or game["trashed_at"] is not None
            or game["hidden_at"] is not None
            or game["import_batch_id"] is not None
            or type(game["started_at"]) is not datetime
            or game["started_at"].utcoffset() is None
        ):
            raise StartedSnapshotUnavailable
        away, home = (
            _uuid(game[name]) for name in ("away_team_record_id", "home_team_record_id")
        )
        if away == home:
            raise StartedSnapshotUnavailable
        current = _one(
            run(RecordingGenerationReadToken(game_id)), _GENERATION_READ_COLUMNS
        )
        generation = current["generation"]
        if type(generation) is not int or not 0 < generation <= 2**63 - 1:
            raise StartedSnapshotUnavailable
        locked_generation = _one(
            run(RecordingGenerationLockToken(game_id, generation)),
            _GENERATION_READ_COLUMNS,
        )
        if (
            current != locked_generation
            or current["tenant_id"] != tenant
            or current["game_id"] != game_id
            or current["kind"] != "normal"
            or current["revoked_at"] is not None
            or current["retired_at"] is not None
            or current["import_batch_id"] is not None
            or any(
                type(current[k]) is not int or current[k] != 0
                for k in ("confirmed_watermark", "applied_prefix")
            )
        ):
            raise StartedSnapshotUnavailable
        rows = _rows(run(StartedLineupsReadToken(game_id)), LINEUP_COLUMNS)
        if len(rows) != 2 or any(
            r["tenant_id"] != tenant or r["game_id"] != game_id for r in rows
        ):
            raise StartedSnapshotUnavailable
        lineups = tuple(_saved_lineup(row) for row in rows)
        if len({lineup.id for lineup in lineups}) != 2 or {
            x.team_id for x in lineups
        } != {away, home}:
            raise StartedSnapshotUnavailable
        sides = tuple(
            next(x for x in lineups if x.team_id == team) for team in (away, home)
        )
        players = set()
        for lineup in sides:
            for entry in lineup.entries:
                identifier = UUID(entry.roster.player_id)
                if identifier in players:
                    raise StartedSnapshotUnavailable
                players.add(identifier)
                token = PlayerReadToken(
                    1,
                    record_id=identifier,
                    team_record_id=lineup.team_id,
                    include_hidden=True,
                )
                selected = tuple(player_read_statement(token).selected_columns.keys())
                player = _one(run(token), selected)
                if (
                    player["id"] != identifier
                    or player["team_record_id"] != lineup.team_id
                ):
                    raise StartedSnapshotUnavailable
        for token_type in (
            StartedEventSlotsExistenceToken,
            StartedOperationEventsExistenceToken,
            StartedPlayRowsExistenceToken,
        ):
            if _rows(run(token_type(game_id)), ("game_id",)):
                raise StartedSnapshotUnavailable
        raw_rules = _plain(game["applied_rules"])
        rules = _saved_start_rule_wire(raw_rules)
        request = InitialGameRosterRequest.model_validate_json(
            json.dumps(
                {
                    "dh": rules.dh,
                    **{
                        name: {
                            "team_id": str(lineup.team_id),
                            "entries": [
                                e.roster.model_dump(mode="json") for e in lineup.entries
                            ],
                        }
                        for name, lineup in zip(("away", "home"), sides, strict=True)
                    },
                }
            ),
            by_alias=True,
            by_name=False,
        )
        result = evaluate_initial_game_roster(request)
        if (
            result.ok is not True
            or handle._state_key is not state_key
            or handle._bound_tenant_id != tenant
        ):
            raise StartedSnapshotUnavailable
        return StartedInitialSnapshot(
            tenant,
            game_id,
            game["started_at"],
            generation,
            0,
            0,
            (sides[0], sides[1]),
            json.dumps(raw_rules, sort_keys=True, separators=(",", ":")),
            _initial_before(),
            rules,
            result.value,
        )
    except (ValueError, TypeError, KeyError, RuntimeError):
        raise StartedSnapshotUnavailable from None
