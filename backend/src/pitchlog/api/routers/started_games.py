"""開始済み試合の保存値をtenant限定で再取得する。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from pitchlog.api.schemas.started_games import (
    StartedGameRead,
    StartedLineup,
    StartedLineupEntry,
    StartedLineups,
)
from pitchlog.api.tenant_access import TenantMatchedRoute, require_tenant_access
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.started_read import (
    StartedGameView,
    StartedReadNotVisible,
    StartedReadRecorded,
    read_started_game,
)
from pitchlog.repositories.started_snapshot import SavedStartedLineup
from pitchlog.repositories.transaction import tenant_transaction_scope

router = APIRouter(tags=["開始済み試合"], route_class=TenantMatchedRoute)


def _lineup(source: SavedStartedLineup) -> StartedLineup:
    """保存済みlineupを、現在の名簿値を混ぜずに応答へ写す。"""
    return StartedLineup(
        lineup_id=source.id,
        team_record_id=source.team_id,
        entries=[
            StartedLineupEntry(
                player_id=UUID(entry.roster.player_id),
                batting_order=entry.roster.batting_order,
                fielding_position=entry.roster.fielding_position,
                uniform_number_snapshot=entry.uniform_number_snapshot,
            )
            for entry in source.entries
        ],
    )


def _read(view: StartedGameView) -> StartedGameRead:
    """scope内で組立結果とDTOの全keyを検証する。"""
    return StartedGameRead.model_validate(
        {
            "read_kind": "initial",
            "id": view.game_id,
            "scheduled_at": view.scheduled_at,
            "game_type_key": view.game_type_key,
            "tournament_key": view.tournament_key,
            "away_team_record_id": view.away_team_record_id,
            "home_team_record_id": view.home_team_record_id,
            "plate_umpire": view.plate_umpire,
            "section_label": view.section_label,
            "week_label": view.week_label,
            "day_label": view.day_label,
            "game_number_label": view.game_number_label,
            "status": "in_progress",
            "started_at": view.started_at,
            "applied_rules": view.applied_rules,
            "lineups": StartedLineups(
                away=_lineup(view.lineups[0]), home=_lineup(view.lineups[1])
            ),
            "roster": view.roster,
            "state": view.before,
            "current_d4": view.current_d4,
        }
    )


@router.get(
    "/games/{game_id}/started",
    response_model=StartedGameRead,
    operation_id="started_game_detail",
)
def read_started_game_detail(
    game_id: UUID,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> StartedGameRead:
    """不可視・別tenant・不存在を同じ404へ閉じ、記録後は409を返す。"""
    try:
        with tenant_transaction_scope(context) as scope:
            result = read_started_game(scope, game_id)
            item = _read(result) if type(result) is StartedGameView else None
    except Exception:
        # rollback後に固定外形だけを返し、DB値や原例外を公開しない。
        raise HTTPException(status_code=503) from None
    if type(result) is StartedReadNotVisible:
        raise HTTPException(status_code=404)
    if type(result) is StartedReadRecorded:
        raise HTTPException(status_code=409)
    if item is None:
        raise HTTPException(status_code=503)
    return item
