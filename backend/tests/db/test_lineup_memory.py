"""直近スタメンの保存とテナント境界を実 PostgreSQL で検証する。"""

from __future__ import annotations

import secrets
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import MappingProxyType
from typing import Any
from uuid import UUID

import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from sqlalchemy.engine import URL
from test_authz_tenant_context import make_tenant_context

from pitchlog.authz.runtime_contract import APPLICATION_ROLE_NAME
from pitchlog.repositories.lineup_memory import (
    LineupMemoryReadToken,
    LineupMemoryUnavailable,
    save_lineup_memory,
)
from pitchlog.repositories.transaction import tenant_transaction_scope

from .conftest import ProvisionedProductCatalog

pytestmark = pytest.mark.requires_db

_TENANT_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_TENANT_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_TEAM_A = UUID("aaaaaaaa-0000-0000-0000-000000000001")
_PLAYER_A = UUID("aaaaaaaa-0000-0000-0000-000000000002")
_OPPONENT_A = UUID("aaaaaaaa-0000-0000-0000-000000000003")
_OPPONENT_PLAYER_A = UUID("aaaaaaaa-0000-0000-0000-000000000004")
_MISSING_PLAYER = UUID("aaaaaaaa-0000-0000-0000-000000000005")


def _application_url(dsn: str) -> str:
    """使い捨て DB のアプリロール DSN を SQLAlchemy URL にする。"""
    values = conninfo_to_dict(dsn)
    username = values.get("user")
    password = values.get("password")
    host = values.get("host")
    port = values.get("port")
    database = values.get("dbname")
    return URL.create(
        "postgresql+psycopg",
        username=None if username is None else str(username),
        password=None if password is None else str(password),
        host=None if host is None else str(host),
        port=None if port is None else int(port),
        database=None if database is None else str(database),
        query={"sslmode": "disable"},
    ).render_as_string(hide_password=False)


@pytest.fixture
def lineup_database(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> ProvisionedProductCatalog:
    """2 テナントと現役選手を作り、製品接続 URL を設定する。"""
    catalog = provisioned_product_catalog
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO tenants (id, name, enabled) "
            "VALUES (%s, %s, true), (%s, %s, true)",
            (_TENANT_A, "lineup-a", _TENANT_B, "lineup-b"),
        )
        cursor.execute(
            "INSERT INTO team_records (tenant_id, id, kind, name) "
            "VALUES (%s, %s, 'self', %s)",
            (_TENANT_A, _TEAM_A, "lineup-team-a"),
        )
        cursor.execute(
            "INSERT INTO players (tenant_id, id, team_record_id, name, "
            "roster_status_key) VALUES (%s, %s, %s, %s, 'active')",
            (_TENANT_A, _PLAYER_A, _TEAM_A, "lineup-player-a"),
        )
        password = secrets.token_urlsafe(24)
        cursor.execute(
            sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                sql.Identifier(APPLICATION_ROLE_NAME),
                sql.Literal(password),
            )
        )
    catalog.applicator.commit()
    dsn = make_conninfo(
        catalog.owner_dsn,
        user=APPLICATION_ROLE_NAME,
        password=password,
    )
    monkeypatch.setenv("PITCHLOG_DATABASE_URL", _application_url(dsn))
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")
    return catalog


def _lineup(position: str) -> tuple[dict[str, object], ...]:
    """確定済み要素の ID と順序を試験用に作る。"""
    return (
        {
            "player_id": str(_PLAYER_A),
            "batting_order": 1,
            "fielding_position": position,
        },
    )


def test_save_updates_one_memory_and_rolls_back(
    lineup_database: ProvisionedProductCatalog,
) -> None:
    """初回挿入・再保存・失敗時取消を同じ実 DB で確かめる。"""
    with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
        save_lineup_memory(scope, _TEAM_A, _lineup("first"))
    with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
        save_lineup_memory(scope, _TEAM_A, _lineup("second"))
        result = scope.run(LineupMemoryReadToken(_TEAM_A))
        lineup = result.rows[0][1]
        assert isinstance(lineup, tuple)
        slot = lineup[0]
        assert isinstance(slot, MappingProxyType)
        assert slot["fielding_position"] == "second"

    with pytest.raises(RuntimeError, match="取消"):
        with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
            save_lineup_memory(scope, _TEAM_A, _lineup("rolled-back"))
            raise RuntimeError("取消")

    with lineup_database.observer.cursor() as cursor:
        cursor.execute(
            "SELECT lineup, count(*) OVER () FROM lineup_memories "
            "WHERE tenant_id = %s AND team_record_id = %s AND retired_at IS NULL",
            (_TENANT_A, _TEAM_A),
        )
        rows: list[tuple[Any, ...]] = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][1] == 1
    assert rows[0][0][0]["fielding_position"] == "second"


def test_other_tenant_and_missing_player_cannot_save(
    lineup_database: ProvisionedProductCatalog,
) -> None:
    """別テナントの self チームと名簿から消えた選手を拒否する。"""
    with tenant_transaction_scope(make_tenant_context(_TENANT_B)) as scope:
        with pytest.raises(LineupMemoryUnavailable):
            save_lineup_memory(scope, _TEAM_A, _lineup("first"))

    with lineup_database.applicator.cursor() as cursor:
        cursor.execute(
            "UPDATE players SET hidden_at = now() WHERE tenant_id = %s AND id = %s",
            (_TENANT_A, _PLAYER_A),
        )
    lineup_database.applicator.commit()
    with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
        with pytest.raises(LineupMemoryUnavailable):
            save_lineup_memory(scope, _TEAM_A, _lineup("first"))


def test_concurrent_first_saves_keep_the_later_commit(
    lineup_database: ProvisionedProductCatalog,
) -> None:
    """初回挿入の競合をチーム行で直列化し、直近 1 件に収める。"""
    first_saved = Event()
    release_first = Event()
    second_started = Event()
    second_saved = Event()

    def first() -> None:
        with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
            save_lineup_memory(scope, _TEAM_A, _lineup("first"))
            first_saved.set()
            assert release_first.wait(10)

    def second() -> None:
        second_started.set()
        with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
            save_lineup_memory(scope, _TEAM_A, _lineup("second"))
            second_saved.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_result = pool.submit(first)
        assert first_saved.wait(10)
        second_result = pool.submit(second)
        try:
            assert second_started.wait(10)
            assert not second_saved.wait(0.2)
        finally:
            release_first.set()
        first_result.result(timeout=10)
        second_result.result(timeout=10)

    with lineup_database.observer.cursor() as cursor:
        cursor.execute(
            "SELECT lineup FROM lineup_memories WHERE tenant_id = %s "
            "AND team_record_id = %s AND retired_at IS NULL",
            (_TENANT_A, _TEAM_A),
        )
        rows: list[tuple[Any, ...]] = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][0][0]["fielding_position"] == "second"


def test_nonactive_missing_and_other_team_players_cannot_save(
    lineup_database: ProvisionedProductCatalog,
) -> None:
    """非現役・欠損・別チームの ID を確定記憶へ混入させない。"""
    for status in ("other", "ob"):
        with lineup_database.applicator.cursor() as cursor:
            cursor.execute(
                "UPDATE players SET roster_status_key = %s "
                "WHERE tenant_id = %s AND id = %s",
                (status, _TENANT_A, _PLAYER_A),
            )
        lineup_database.applicator.commit()
        with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
            with pytest.raises(LineupMemoryUnavailable):
                save_lineup_memory(scope, _TEAM_A, _lineup("first"))

    with lineup_database.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO team_records (tenant_id, id, kind, name) "
            "VALUES (%s, %s, 'opponent', %s)",
            (_TENANT_A, _OPPONENT_A, "lineup-opponent"),
        )
        cursor.execute(
            "INSERT INTO players (tenant_id, id, team_record_id, name, "
            "roster_status_key) VALUES (%s, %s, %s, %s, 'active')",
            (_TENANT_A, _OPPONENT_PLAYER_A, _OPPONENT_A, "opponent-player"),
        )
    lineup_database.applicator.commit()
    for player_id in (_MISSING_PLAYER, _OPPONENT_PLAYER_A):
        entry = ({**_lineup("first")[0], "player_id": str(player_id)},)
        with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
            with pytest.raises(LineupMemoryUnavailable):
                save_lineup_memory(scope, _TEAM_A, entry)
