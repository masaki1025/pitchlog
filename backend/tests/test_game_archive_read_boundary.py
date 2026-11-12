"""試合一覧（準備中・進行中・終了）の閉じた read 境界を検査する。"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute

from pitchlog.api.routers import games as games_router
from pitchlog.api.routers.games import _archive_page
from pitchlog.api.schemas.games import (
    GameArchiveListRequest,
    decode_preparing_game_cursor,
)
from pitchlog.repositories.base import _operation_spec, _validate_prepared_statement
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.games import (
    GAME_ARCHIVE_READ_OPERATIONS,
    GameArchiveFinishedListToken,
    GameArchiveInProgressListToken,
    GameArchivePreparingListToken,
    PreparingGameListToken,
)

_ARCHIVE_TOKENS = (
    (GameArchivePreparingListToken, "preparing"),
    (GameArchiveInProgressListToken, "in_progress"),
    (GameArchiveFinishedListToken, "finished"),
)


@pytest.mark.parametrize(("token_type", "status"), _ARCHIVE_TOKENS)
def test_archive_registration_accepts_only_its_status(
    token_type: type, status: str
) -> None:
    """各登録は宣言した1状態の束縛値だけを受理する。"""
    spec = next(
        item for item in GAME_ARCHIVE_READ_OPERATIONS if item.token_type is token_type
    )
    _validate_prepared_statement(
        spec,
        spec.statement,
        {"tenant_id": uuid4(), "status": status, "limit": 2},
    )
    other = "finished" if status != "finished" else "preparing"
    with pytest.raises(RuntimeError, match="status"):
        _validate_prepared_statement(
            spec,
            spec.statement,
            {"tenant_id": uuid4(), "status": other, "limit": 2},
        )


@pytest.mark.parametrize(("token_type", "status"), _ARCHIVE_TOKENS)
def test_archive_tokens_are_registered_exactly(token_type: type, status: str) -> None:
    """製品 registry は3状態の token をそれぞれの登録へ解決する。"""
    spec = next(
        item for item in GAME_ARCHIVE_READ_OPERATIONS if item.token_type is token_type
    )
    assert _operation_spec(token_type()) is spec
    assert spec.capability_id == "CAP:games:read"


def test_archive_prepare_rejects_other_operation_type() -> None:
    """一覧 prepare へ準備中一覧 token を渡しても状態を混同しない。"""
    with pytest.raises(ValueError, match="試合一覧 token"):
        GAME_ARCHIVE_READ_OPERATIONS[0].prepare(PreparingGameListToken())


def test_archive_page_merges_statuses_and_returns_next_cursor() -> None:
    """状態別の行を日時とIDの降順へ統合し、最後の1件を次cursorへ写す。"""
    team_a, team_b = uuid4(), uuid4()
    older, middle, newer = (
        datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc),
    )
    ids = (uuid4(), uuid4(), uuid4())
    rows = tuple(
        (
            ids[index],
            scheduled_at,
            "game_official",
            "tournament",
            team_a,
            team_b,
            status,
            None,
        )
        for index, (scheduled_at, status) in enumerate(
            (
                (older, "preparing"),
                (newer, "in_progress"),
                (middle, "finished"),
            )
        )
    )
    page = _archive_page(rows, 2)
    assert [item.id for item in page.items] == [ids[1], ids[2]]
    assert page.next_cursor is not None
    assert decode_preparing_game_cursor(page.next_cursor) == (middle, ids[2])


def test_archive_page_without_extra_row_has_no_cursor() -> None:
    """上限以内の行だけなら次cursorを発行しない。"""
    team_a, team_b = uuid4(), uuid4()
    game_id = uuid4()
    page = _archive_page(
        (
            (
                game_id,
                datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc),
                "game_official",
                "tournament",
                team_a,
                team_b,
                "finished",
                None,
            ),
        ),
        2,
    )
    assert [item.id for item in page.items] == [game_id]
    assert page.next_cursor is None


def test_archive_token_rejects_invalid_limit_and_cursor() -> None:
    """件数と cursor は実行前に閉じた範囲へ制限する。"""
    with pytest.raises(ValueError, match="limit"):
        GameArchivePreparingListToken(limit=0)
    with pytest.raises(ValueError, match="カーソル"):
        GameArchivePreparingListToken(cursor="not-a-cursor")
    assert GameArchivePreparingListToken(limit=1).limit == 1


def test_archive_route_runs_three_statuses_and_merges(monkeypatch) -> None:
    """API は3状態を別tokenで読み、1ページへ統合して次cursorを返す。"""
    team_a, team_b = uuid4(), uuid4()
    ids = (uuid4(), uuid4(), uuid4())
    times = (
        datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc),
    )

    def row(index: int, status: str) -> tuple[object, ...]:
        return (
            ids[index],
            times[index],
            "game_official",
            "tournament",
            team_a,
            team_b,
            status,
            None,
        )

    rows_by_token = {
        GameArchivePreparingListToken: (row(0, "preparing"),),
        GameArchiveInProgressListToken: (row(2, "in_progress"),),
        GameArchiveFinishedListToken: (row(1, "finished"),),
    }
    seen: list[type] = []

    class Scope:
        def run(self, token):
            seen.append(type(token))
            return SimpleNamespace(rows=rows_by_token[type(token)])

    @contextmanager
    def scope(_context):
        yield Scope()

    monkeypatch.setattr(games_router, "tenant_transaction_scope", scope)
    page = games_router.list_game_archive(
        GameArchiveListRequest(limit=2),
        cast(TenantContext, object()),
    )
    assert seen == [
        GameArchivePreparingListToken,
        GameArchiveInProgressListToken,
        GameArchiveFinishedListToken,
    ]
    assert [item.id for item in page.items] == [ids[2], ids[1]]
    assert page.next_cursor is not None
    assert decode_preparing_game_cursor(page.next_cursor) == (times[1], ids[1])


def test_archive_route_precedes_parameterized_game_route() -> None:
    """静的 /games/archive が /games/{game_id} に吸われない順序で登録される。"""
    routes = [
        route for route in games_router.router.routes if isinstance(route, APIRoute)
    ]
    paths = [route.path for route in routes]
    archive_index = paths.index("/games/archive")
    detail_index = paths.index("/games/{game_id}")
    assert archive_index < detail_index
    assert routes[archive_index].operation_id == "game_archive_list"
    assert routes[detail_index].operation_id == "preparing_game_detail"
