"""開始済み試合の保存値をtenant限定で再取得する。"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from pitchlog.api.schemas.started_games import (
    StartedGameRead,
    StartedGameReadResponse,
    StartedLineup,
    StartedLineupEntry,
    StartedLineups,
    StartedPlayRow,
    StartedRecordedGameRead,
    StartedRecordedPrefixGameRead,
)
from pitchlog.api.tenant_access import TenantMatchedRoute, require_tenant_access
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.ordinary_prefix_read import (
    OrdinaryPrefixView,
    read_ordinary_prefix,
)
from pitchlog.repositories.recorded_snapshot_operations import (
    RECORDED_PLAY_ROW_COLUMNS,
)
from pitchlog.repositories.started_read import (
    StartedGameView,
    StartedReadNotVisible,
    StartedReadRecorded,
    StartedRecordedView,
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


def _play_row(view: StartedRecordedView) -> StartedPlayRow:
    """照合済み41列を公開列へ写し、座標だけpayloadの正準整数値に置き換える。

    座標は保存Doubleから逆変換しない。``RecordedCalculationCandidate`` が
    payloadと全値一致を確認した正準整数kをそのまま返す。
    """
    row = dict(zip(RECORDED_PLAY_ROW_COLUMNS, view.play_row, strict=True))
    public = {
        name: row[name] for name in StartedPlayRow.model_fields if name != "course"
    }
    public["course"] = view.play_course
    return StartedPlayRow.model_validate(public)


def _read_recorded(view: StartedRecordedView) -> StartedRecordedGameRead:
    """記録後の保存初球を、initialと同形＋after/history/flags/T2/PlayRowで返す。"""
    return StartedRecordedGameRead.model_validate(
        {
            "read_kind": "recorded",
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
            # `state` は initial と同じ before。記録後は別key `after` に分ける。
            "state": view.before,
            "after": view.after,
            "history": list(view.history),
            "stat_flags": view.stat_flags,
            "t2": view.t2,
            "play_rows": [_play_row(view)],
            "current_d4": view.current_d4,
        }
    )


@router.get(
    "/games/{game_id}/started",
    response_model=StartedGameReadResponse,
    operation_id="started_game_detail",
)
def read_started_game_detail(
    game_id: UUID,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
    projection: Literal["ordinary-prefix-v1"] | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(min_length=1, max_length=2048)] = None,
) -> StartedGameRead | StartedRecordedGameRead | Response:
    """不可視・別tenant・不存在は404、保存初球は200、他の記録は409を返す。"""
    try:
        with tenant_transaction_scope(context) as scope:
            if projection == "ordinary-prefix-v1":
                prefix = read_ordinary_prefix(
                    scope, game_id, limit=limit, cursor=cursor
                )
                if type(prefix) is OrdinaryPrefixView:
                    metadata = _read(prefix.metadata).model_dump(
                        mode="python", by_alias=True
                    )
                    value = StartedRecordedPrefixGameRead.model_validate(
                        {
                            **metadata,
                            "read_kind": "recorded-prefix",
                            **prefix.projection,
                        }
                    )
                    # 未提示History軸をnull補完しない。旧応答serializerは不変。
                    return Response(
                        value.model_dump_json(by_alias=True, exclude_unset=True),
                        media_type="application/json",
                    )
                result = prefix
                item = None
            else:
                result = read_started_game(scope, game_id)
            if type(result) is StartedGameView:
                item: StartedGameRead | StartedRecordedGameRead | None = _read(result)
            elif type(result) is StartedRecordedView:
                item = _read_recorded(result)
            else:
                item = None
    except Exception:
        # rollback後に固定外形だけを返し、DB値や原例外を公開しない。
        raise HTTPException(status_code=503) from None
    if type(result) is StartedReadNotVisible:
        raise HTTPException(status_code=404)
    if type(result) is StartedReadRecorded:
        # 2球目以降・訂正・墓標・失効世代など、初球1件を閉じて返せない記録。
        raise HTTPException(status_code=409)
    if item is None:
        raise HTTPException(status_code=503)
    return item
