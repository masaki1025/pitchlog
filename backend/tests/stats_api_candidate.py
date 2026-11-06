"""基本成績のtenant限定read API。"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from stats_basic_candidate import ReadBasicStatsToken
from stats_schemas_candidate import (
    Category,
    GameBasicStats,
    PlayerBasicStats,
    SeasonBasicStats,
)

from pitchlog.api.tenant_access import require_tenant_access
from pitchlog.exports.csv import CsvCell, stream_csv
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.transaction import stats_primitive_read_scope
from pitchlog.stats.basic_stats import (
    BATTING_ITEMS,
    COUNT_METRIC_IDS,
    PITCHING_ITEMS,
    build_basic_stats,
)

router = APIRouter(tags=["基本成績"])

_JST = timezone(timedelta(hours=9), "JST")
_CATEGORY_KEYS = {
    "official": "game_official,game_semi_official",
    "practice": "game_open,game_intrasquad,game_other",
    "all": ("game_official,game_semi_official,game_open,game_intrasquad,game_other"),
}
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _invalid_constant(_: str) -> None:
    """JSONのNaN/Infinityを拒否する。"""
    raise ValueError("非有限値は成績応答に含められません")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """重複keyを後勝ちで消さない。"""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("成績JSONに重複keyがあります")
        result[key] = value
    return result


def _metrics(payload: object) -> dict[str, dict[str, Any]]:
    """DB関数の閉26 metric JSONを検証し、整数へ戻す。"""
    if type(payload) is not str:
        raise ValueError("成績JSONの型が不正です")
    data = json.loads(
        payload,
        object_pairs_hook=_unique_object,
        parse_constant=_invalid_constant,
    )
    # 26十分統計に、27番目以降の正式metric（登板/打者数）が加わっても
    # 同じ表示層で消費できる。未知metricは拒否する。
    allowed = set(COUNT_METRIC_IDS) | {"appearances", "batters_faced"}
    if type(data) is not dict or not set(COUNT_METRIC_IDS) <= set(data) <= allowed:
        raise ValueError("成績JSONの閉集合が不一致です")
    result: dict[str, dict[str, Any]] = {}
    for metric_id, row in data.items():
        if (
            type(row) is not dict
            or set(row) != {"state", "value"}
            or row["state"] not in ("available", "source_unavailable")
        ):
            raise ValueError("成績metric行の型が不正です")
        value = row["value"]
        if row["state"] == "source_unavailable":
            if value is not None:
                raise ValueError("不足metricに値があります")
            result[metric_id] = {"state": "source_unavailable", "value": None}
        else:
            if (
                type(value) is not str
                or len(value) > 10000
                or re.fullmatch(r"0|[1-9][0-9]*", value) is None
            ):
                raise ValueError("成績metricの値が非正準です")
            result[metric_id] = {"state": "available", "value": int(value)}
    return result


def _players(
    rows: tuple[tuple[Any, ...], ...], limit: int
) -> tuple[list[PlayerBasicStats], str | None]:
    """固定行を検証し、limit+1の最後をcursorへ送る。"""
    if type(rows) is not tuple or len(rows) > limit + 1:
        raise ValueError("成績行数が不正です")
    players: list[PlayerBasicStats] = []
    for row in rows[:limit]:
        if type(row) is not tuple or len(row) != 6:
            raise ValueError("成績行の型が不正です")
        player_id, name, uniform, team_id, team_name, payload = row
        if (
            type(player_id) is not UUID
            or type(name) is not str
            or type(uniform) is not str
            or type(team_id) is not UUID
            or type(team_name) is not str
        ):
            raise ValueError("成績行の列型が不正です")
        built = build_basic_stats(_metrics(payload))
        players.append(
            PlayerBasicStats(
                player_id=player_id,
                player_name=name,
                uniform_number=uniform,
                team_record_id=team_id,
                team_name=team_name,
                is_pitcher=built["is_pitcher"],
                batting=built["batting"],
                pitching=built["pitching"],
                pending=[value for value in built["pending"] if value is not None],
            )
        )
    cursor = str(rows[limit - 1][0]) if len(rows) > limit else None
    return players, cursor


def _reject_as_not_found(error: Exception) -> NoReturn:
    """関数境界の拒否/未存在を、値を漏らさない404へ写す。"""
    original = getattr(error, "orig", None)
    if getattr(original, "sqlstate", None) == "42501":
        raise HTTPException(status_code=404) from None
    raise HTTPException(status_code=503) from None


_CSV_HEADERS = (
    "player_id",
    "player_name",
    "uniform_number",
    "team_name",
    "is_pitcher",
    *("batting_" + item[0] for item in BATTING_ITEMS),
    *("pitching_" + item[0] for item in PITCHING_ITEMS),
    "pending",
    "source_unavailable_metrics",
)


def _csv_row(player: PlayerBasicStats) -> tuple[CsvCell, ...]:
    """同じAPI表示値をCSVセルへ写す。未取得を0へ変えない。"""
    batting = {item.metric_id: item for item in player.batting}
    pitching = {item.metric_id: item for item in player.pitching}
    values: list[CsvCell] = [
        str(player.player_id),
        player.player_name,
        player.uniform_number,
        player.team_name,
        "1" if player.is_pitcher else "0",
    ]
    unavailable = []
    for metric_id, _, _ in BATTING_ITEMS:
        item = batting[metric_id]
        values.append(item.display if item.state == "available" else "")
        if item.state == "source_unavailable":
            unavailable.append(metric_id)
    for metric_id, _, _ in PITCHING_ITEMS:
        item = pitching[metric_id]
        values.append(item.display if item.state == "available" else "")
        if item.state == "source_unavailable":
            unavailable.append(metric_id)
    values.append(";".join(player.pending))
    values.append(";".join(unavailable))
    return tuple(values)


def _iter_players(
    context: TenantContext,
    *,
    game_id: UUID | None,
    mode: str,
    year: int | None,
    category: Category,
) -> Iterator[PlayerBasicStats]:
    """同じRR snapshotで全ページを逐次返し、CSVを有限にstreamする。"""
    page_size = 200
    with stats_primitive_read_scope(context) as scope:
        cursor = None
        while True:
            if game_id is not None:
                token = ReadBasicStatsToken(
                    game_id=str(game_id),
                    year_start="",
                    year_end="",
                    category="all",
                    official=mode == "official",
                    after_player_id=cursor or "",
                    page_size=page_size,
                )
            else:
                assert year is not None
                start, end = _jst_boundaries(year)
                token = ReadBasicStatsToken(
                    game_id="",
                    year_start=start,
                    year_end=end,
                    category=category,
                    official=True,
                    after_player_id=cursor or "",
                    page_size=page_size,
                )
            result = scope.run_function(token)
            players, next_cursor = _players(result.rows, page_size)
            yield from players
            if next_cursor is None:
                return
            cursor = next_cursor


def _csv_stream_response(
    context: TenantContext,
    *,
    game_id: UUID | None,
    mode: str,
    year: int | None,
    category: Category,
    filename: str,
) -> StreamingResponse:
    """全ページを一時ファイルへ完成させてから返し、部分CSVを成功保存しない。"""
    spool = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    try:
        players = _iter_players(
            context, game_id=game_id, mode=mode, year=year, category=category
        )
        for chunk in stream_csv(_CSV_HEADERS, (_csv_row(p) for p in players)):
            spool.write(chunk)
        spool.seek(0)
    except BaseException:
        spool.close()
        raise

    def chunks() -> Iterator[bytes]:
        try:
            while True:
                data = spool.read(65536)
                if not data:
                    return
                yield data
        finally:
            spool.close()

    return StreamingResponse(
        chunks(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/games/{game_id}/stats.csv",
    operation_id="game_basic_stats_csv",
)
def download_game_basic_stats_csv(
    game_id: UUID,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
    mode: Annotated[str, Query(pattern="^(current|official)$")] = "current",
) -> StreamingResponse:
    """試合別成績CSVを同じRR snapshotから完成させて返す。"""
    try:
        return _csv_stream_response(
            context,
            game_id=game_id,
            mode=mode,
            year=None,
            category="all",
            filename=f"game-basic-stats-{game_id}-{mode}.csv",
        )
    except HTTPException:
        raise
    except Exception as error:
        _reject_as_not_found(error)


@router.get(
    "/stats/seasons/{year}/stats.csv",
    operation_id="season_basic_stats_csv",
)
def download_season_basic_stats_csv(
    year: int,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
    category: Annotated[Category, Query()] = "all",
) -> StreamingResponse:
    """JST暦年成績CSVを終了確定した最新版だけで完成させて返す。"""
    if not 1 <= year <= 9999 or category not in _CATEGORY_KEYS:
        raise HTTPException(status_code=400)
    try:
        return _csv_stream_response(
            context,
            game_id=None,
            mode="official",
            year=year,
            category=category,
            filename=f"season-basic-stats-{year}-{category}.csv",
        )
    except HTTPException:
        raise
    except Exception as error:
        _reject_as_not_found(error)


@router.get(
    "/games/{game_id}/stats",
    response_model=GameBasicStats,
    operation_id="game_basic_stats",
)
def read_game_basic_stats(
    game_id: UUID,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
    mode: Annotated[str, Query(pattern="^(current|official)$")] = "current",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> GameBasicStats:
    """試合の基本成績を公式/暫定で返す。認可はtenant文脈だけを使う。"""
    if cursor is not None and _UUID_RE.fullmatch(cursor) is None:
        raise HTTPException(status_code=400)
    token = ReadBasicStatsToken(
        game_id=str(game_id),
        year_start="",
        year_end="",
        category="all",
        official=mode == "official",
        after_player_id=cursor or "",
        page_size=limit,
    )
    try:
        with stats_primitive_read_scope(context) as scope:
            result = scope.run_function(token)
        players, next_cursor = _players(result.rows, limit)
    except HTTPException:
        raise
    except Exception as error:
        _reject_as_not_found(error)
    parsed_mode = "official" if mode == "official" else "current"
    return GameBasicStats(
        game_id=game_id,
        mode=parsed_mode,
        players=players,
        next_cursor=next_cursor,
    )


def _jst_boundaries(year: int) -> tuple[str, str]:
    """JST暦年の [start,end) をUTC offset付きISO文字列で返す。"""
    start = datetime(year, 1, 1, tzinfo=_JST)
    # PostgreSQL timestamptzは西暦10000年境界を扱える。
    # Python datetimeの上限を越すため文字列化する。
    end = f"{year + 1:04d}-01-01T00:00:00+09:00"
    return start.isoformat(), end


@router.get(
    "/stats/seasons/{year}",
    response_model=SeasonBasicStats,
    operation_id="season_basic_stats",
)
def read_season_basic_stats(
    year: int,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
    category: Annotated[Category, Query()] = "all",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> SeasonBasicStats:
    """JST暦年の基本成績を終了確定した最新版だけで返す。"""
    if not 1 <= year <= 9999:
        raise HTTPException(status_code=400)
    if cursor is not None and _UUID_RE.fullmatch(cursor) is None:
        raise HTTPException(status_code=400)
    if category not in _CATEGORY_KEYS:
        raise HTTPException(status_code=400)
    start, end = _jst_boundaries(year)
    token = ReadBasicStatsToken(
        game_id="",
        year_start=start,
        year_end=end,
        category=category,
        official=True,
        after_player_id=cursor or "",
        page_size=limit,
    )
    try:
        with stats_primitive_read_scope(context) as scope:
            result = scope.run_function(token)
        players, next_cursor = _players(result.rows, limit)
    except HTTPException:
        raise
    except Exception as error:
        _reject_as_not_found(error)
    return SeasonBasicStats(
        year=year,
        category=category,
        period_label=f"{year}年通算",
        players=players,
        next_cursor=next_cursor,
    )
