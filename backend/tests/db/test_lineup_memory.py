"""直近スタメンの保存とテナント境界を実 PostgreSQL で検証する。"""

from __future__ import annotations

import json
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import MappingProxyType
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from test_authz_tenant_context import make_tenant_context

from pitchlog.api.routers import players as player_router
from pitchlog.api.schemas.roster import PlayerStatusBulkRequest
from pitchlog.authz.runtime_contract import APPLICATION_ROLE_NAME
from pitchlog.db.engine import create_database_engine
from pitchlog.repositories import base as base_module
from pitchlog.repositories import transaction as transaction_module
from pitchlog.repositories.base import TenantRepositoryBase
from pitchlog.repositories.lineup_memory import (
    LineupMemoryReadToken,
    LineupMemoryUnavailable,
    _ActiveLineupPlayerLockToken,
    _LineupMemoryInsertToken,
    _LineupMemoryUpdateToken,
    _SelfTeamLockToken,
    save_lineup_memory,
)
from pitchlog.repositories.tokens import TenantOperationToken
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
_NUMERIC_PLAYER = UUID("12345678-1234-1234-1234-123456789012")


class _DirectLineupRepository(TenantRepositoryBase):
    """公開リポジトリ実行境界からの直接 token 実行を試す。"""

    def __init__(self, session: Session) -> None:
        self._bound_session = session

    @property
    def _session(self) -> Session:
        return self._bound_session


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


def _write_token(
    kind: str, memory_id: UUID | None, position: str
) -> TenantOperationToken:
    """競合検証で初回保存と既存行更新を同じ手順で作る。"""
    lineup_json = json.dumps(_lineup(position))
    if kind == "insert":
        return _LineupMemoryInsertToken(uuid4(), _TEAM_A, lineup_json)
    assert memory_id is not None
    return _LineupMemoryUpdateToken(memory_id, _TEAM_A, lineup_json)


def _change_player(
    catalog: ProvisionedProductCatalog,
    change: str,
    started: Event | None = None,
    release: Event | None = None,
    attempted: Event | None = None,
    backend_pid: list[int] | None = None,
) -> None:
    """別接続で在籍変更または論理削除を確定する。"""
    admin_dsn = make_conninfo(
        catalog.cluster.admin_dsn,
        dbname=conninfo_to_dict(catalog.owner_dsn)["dbname"],
    )
    with psycopg.connect(admin_dsn) as connection:
        with connection.cursor() as cursor:
            if attempted is not None:
                cursor.execute("SELECT pg_backend_pid()")
                row = cursor.fetchone()
                assert row is not None and isinstance(row[0], int)
                assert backend_pid is not None
                backend_pid.append(row[0])
                attempted.set()
            if change == "status":
                cursor.execute(
                    "UPDATE players SET roster_status_key = 'ob' "
                    "WHERE tenant_id = %s AND id = %s",
                    (_TENANT_A, _PLAYER_A),
                )
            else:
                cursor.execute(
                    "UPDATE players SET hidden_at = now() "
                    "WHERE tenant_id = %s AND id = %s",
                    (_TENANT_A, _PLAYER_A),
                )
            assert cursor.rowcount == 1
            if started is not None:
                started.set()
            if release is not None:
                assert release.wait(10)


def _wait_for_row_lock(catalog: ProvisionedProductCatalog, pid: int) -> None:
    """別接続が実際に PostgreSQL の行ロックを待つまで観測する。"""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with catalog.observer.cursor() as cursor:
            cursor.execute("SELECT pg_blocking_pids(%s)", (pid,))
            row = cursor.fetchone()
        catalog.observer.rollback()
        if row is not None and row[0]:
            return
        time.sleep(0.02)
    pytest.fail("在籍変更接続が選手行ロックを待っていない")


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


@pytest.mark.parametrize("change", ("status", "hidden"))
@pytest.mark.parametrize("kind", ("insert", "update"))
@pytest.mark.parametrize("executor", ("scope", "repository"))
def test_player_change_committed_first_rejects_direct_save(
    lineup_database: ProvisionedProductCatalog,
    change: str,
    kind: str,
    executor: str,
) -> None:
    """在籍変更が先に選手行を掴むと保存は待ち、確定後に拒否する。"""
    memory_id: UUID | None = None
    if kind == "update":
        with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
            save_lineup_memory(scope, _TEAM_A, _lineup("before"))
            row_id = scope.run(LineupMemoryReadToken(_TEAM_A)).rows[0][0]
            assert isinstance(row_id, UUID)
            memory_id = row_id
    changed = Event()
    release_change = Event()
    save_started = Event()
    save_finished = Event()

    def save() -> None:
        save_started.set()
        try:
            with pytest.raises(LineupMemoryUnavailable):
                operation = _write_token(kind, memory_id, "race")
                if executor == "scope":
                    with tenant_transaction_scope(
                        make_tenant_context(_TENANT_A)
                    ) as scope:
                        scope.run(operation)
                else:
                    with Session(create_database_engine()) as session:
                        _DirectLineupRepository(session).execute(
                            make_tenant_context(_TENANT_A), operation
                        )
        finally:
            save_finished.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        change_result = pool.submit(
            _change_player, lineup_database, change, changed, release_change
        )
        if not changed.wait(10):
            change_result.result(timeout=1)
            pytest.fail("在籍変更が行ロックを取得できない")
        save_result = pool.submit(save)
        try:
            assert save_started.wait(10)
            assert not save_finished.wait(0.2)
        finally:
            release_change.set()
        change_result.result(timeout=10)
        save_result.result(timeout=10)

    with lineup_database.observer.cursor() as cursor:
        cursor.execute(
            "SELECT lineup FROM lineup_memories "
            "WHERE tenant_id = %s AND team_record_id = %s",
            (_TENANT_A, _TEAM_A),
        )
        rows = cursor.fetchall()
    if kind == "insert":
        assert rows == []
    else:
        assert rows[0][0][0]["fielding_position"] == "before"


@pytest.mark.parametrize("change", ("status", "hidden"))
@pytest.mark.parametrize("kind", ("insert", "update"))
@pytest.mark.parametrize("executor", ("scope", "repository"))
def test_direct_save_lock_precedes_player_change(
    lineup_database: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
    kind: str,
    executor: str,
) -> None:
    """保存が選手を先にロックすれば在籍変更は保存コミットまで待つ。"""
    memory_id: UUID | None = None
    if kind == "update":
        with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
            save_lineup_memory(scope, _TEAM_A, _lineup("before"))
            row_id = scope.run(LineupMemoryReadToken(_TEAM_A)).rows[0][0]
            assert isinstance(row_id, UUID)
            memory_id = row_id
    ready_to_write = Event()
    release_save = Event()
    change_started = Event()
    change_finished = Event()
    backend_pid: list[int] = []
    executor_module = transaction_module if executor == "scope" else base_module
    original_materialize = executor_module._materialize_execution_result

    def pause_after_player_lock(statement: Any, execution_result: Any) -> Any:
        result = original_materialize(statement, execution_result)
        if "FROM players" in str(statement) and "FOR UPDATE" in str(statement):
            ready_to_write.set()
            assert release_save.wait(10)
        return result

    monkeypatch.setattr(
        executor_module, "_materialize_execution_result", pause_after_player_lock
    )

    def save() -> None:
        operation = _write_token(kind, memory_id, "before-change")
        if executor == "scope":
            with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
                scope.run(operation)
        else:
            with Session(create_database_engine()) as session:
                _DirectLineupRepository(session).execute(
                    make_tenant_context(_TENANT_A), operation
                )

    def change_player() -> None:
        try:
            _change_player(
                lineup_database,
                change,
                attempted=change_started,
                backend_pid=backend_pid,
            )
        finally:
            change_finished.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        save_result = pool.submit(save)
        assert ready_to_write.wait(10)
        change_result = pool.submit(change_player)
        try:
            assert change_started.wait(10)
            _wait_for_row_lock(lineup_database, backend_pid[0])
            assert not change_finished.wait(0.2)
        finally:
            release_save.set()
        save_result.result(timeout=10)
        change_result.result(timeout=10)

    with lineup_database.observer.cursor() as cursor:
        cursor.execute(
            "SELECT lineup FROM lineup_memories "
            "WHERE tenant_id = %s AND team_record_id = %s",
            (_TENANT_A, _TEAM_A),
        )
        row = cursor.fetchone()
    assert row is not None
    assert row[0][0]["fielding_position"] == "before-change"


def test_multiple_players_are_locked_in_uuid_order(
    lineup_database: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """入力順に依存せず在籍一括変更と同じ選手 ID 順でロックする。"""
    second_player = UUID("aaaaaaaa-0000-0000-0000-000000000006")
    with lineup_database.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO players (tenant_id, id, team_record_id, name, "
            "roster_status_key) VALUES (%s, %s, %s, %s, 'active')",
            (_TENANT_A, second_player, _TEAM_A, "second-player"),
        )
    lineup_database.applicator.commit()
    locked: list[UUID] = []
    original_prepare = transaction_module._prepare_operation

    def record_lock(operation: TenantOperationToken, tenant_id: UUID) -> Any:
        if isinstance(operation, _ActiveLineupPlayerLockToken):
            locked.append(operation.player_id)
        return original_prepare(operation, tenant_id)

    monkeypatch.setattr(transaction_module, "_prepare_operation", record_lock)
    lineup = (
        {"player_id": str(second_player), "batting_order": 1, "fielding_position": "P"},
        {"player_id": str(_PLAYER_A), "batting_order": 2, "fielding_position": "C"},
    )
    with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
        scope.run(_LineupMemoryInsertToken(uuid4(), _TEAM_A, json.dumps(lineup)))
    assert locked == sorted((second_player, _PLAYER_A))


def test_bulk_status_and_multi_player_save_do_not_deadlock(
    lineup_database: ProvisionedProductCatalog,
) -> None:
    """選手 A を先に掴んでも、逆順入力の一括変更と保存が循環待機しない。"""
    second_player = UUID("aaaaaaaa-0000-0000-0000-000000000006")
    with lineup_database.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO players (tenant_id, id, team_record_id, name, "
            "roster_status_key) VALUES (%s, %s, %s, %s, 'active')",
            (_TENANT_A, second_player, _TEAM_A, "second-player"),
        )
    lineup_database.applicator.commit()
    lineup = (
        {"player_id": str(second_player), "batting_order": 1, "fielding_position": "P"},
        {"player_id": str(_PLAYER_A), "batting_order": 2, "fielding_position": "C"},
    )
    started = Event()

    def update_status() -> list[UUID]:
        started.set()
        result = player_router.apply_player_status(
            PlayerStatusBulkRequest.model_validate(
                {
                    "player_ids": [str(second_player), str(_PLAYER_A)],
                    "roster_status_key": "ob",
                    "roster_label_key": None,
                }
            ),
            make_tenant_context(_TENANT_A),
        )
        return [player.id for player in result.applied]

    with ThreadPoolExecutor(max_workers=1) as pool:
        with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
            scope.run(_ActiveLineupPlayerLockToken(_TEAM_A, _PLAYER_A))
            status_result = pool.submit(update_status)
            assert started.wait(10)
            time.sleep(0.2)
            scope.run(_LineupMemoryInsertToken(uuid4(), _TEAM_A, json.dumps(lineup)))
        assert status_result.result(timeout=10) == [second_player, _PLAYER_A]

    with lineup_database.observer.cursor() as cursor:
        cursor.execute(
            "SELECT lineup FROM lineup_memories "
            "WHERE tenant_id = %s AND team_record_id = %s",
            (_TENANT_A, _TEAM_A),
        )
        row = cursor.fetchone()
    assert row is not None
    assert [entry["player_id"] for entry in row[0]] == [
        str(second_player),
        str(_PLAYER_A),
    ]


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


def test_direct_insert_token_cannot_bypass_self_and_roster_checks(
    lineup_database: ProvisionedProductCatalog,
) -> None:
    """Helper を通さない登録済み token でも所属と現役性を要求する。"""
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

    attempts = (
        (_OPPONENT_A, _PLAYER_A),
        (_TEAM_A, _MISSING_PLAYER),
        (_TEAM_A, _OPPONENT_PLAYER_A),
    )
    for team_id, player_id in attempts:
        lineup_json = json.dumps([{**_lineup("first")[0], "player_id": str(player_id)}])
        with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
            with pytest.raises(LineupMemoryUnavailable):
                scope.run(_LineupMemoryInsertToken(uuid4(), team_id, lineup_json))

    for status, hidden in (("other", False), ("ob", False), ("active", True)):
        with lineup_database.applicator.cursor() as cursor:
            cursor.execute(
                "UPDATE players SET roster_status_key = %s, hidden_at = "
                "CASE WHEN %s THEN now() ELSE NULL END "
                "WHERE tenant_id = %s AND id = %s",
                (status, hidden, _TENANT_A, _PLAYER_A),
            )
        lineup_database.applicator.commit()
        with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
            with pytest.raises(LineupMemoryUnavailable):
                scope.run(
                    _LineupMemoryInsertToken(
                        uuid4(), _TEAM_A, json.dumps(_lineup("first"))
                    )
                )

    with tenant_transaction_scope(make_tenant_context(_TENANT_B)) as scope:
        with pytest.raises(LineupMemoryUnavailable):
            scope.run(
                _LineupMemoryInsertToken(uuid4(), _TEAM_A, json.dumps(_lineup("first")))
            )


def test_direct_update_token_cannot_replace_memory_with_inactive_player(
    lineup_database: ProvisionedProductCatalog,
) -> None:
    """直接 UPDATE で非現役・削除済み・欠損選手を混入させない。"""
    with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
        save_lineup_memory(scope, _TEAM_A, _lineup("first"))
        memory_id = scope.run(LineupMemoryReadToken(_TEAM_A)).rows[0][0]
    assert isinstance(memory_id, UUID)

    for status, hidden in (("other", False), ("ob", False), ("active", True)):
        with lineup_database.applicator.cursor() as cursor:
            cursor.execute(
                "UPDATE players SET roster_status_key = %s, hidden_at = "
                "CASE WHEN %s THEN now() ELSE NULL END "
                "WHERE tenant_id = %s AND id = %s",
                (status, hidden, _TENANT_A, _PLAYER_A),
            )
        lineup_database.applicator.commit()
        with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
            with pytest.raises(LineupMemoryUnavailable):
                scope.run(
                    _LineupMemoryUpdateToken(
                        memory_id,
                        _TEAM_A,
                        json.dumps(_lineup("changed")),
                    )
                )

    with lineup_database.applicator.cursor() as cursor:
        cursor.execute(
            "UPDATE players SET roster_status_key = 'active', hidden_at = NULL "
            "WHERE tenant_id = %s AND id = %s",
            (_TENANT_A, _PLAYER_A),
        )
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
        with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
            with pytest.raises(LineupMemoryUnavailable):
                scope.run(
                    _LineupMemoryUpdateToken(
                        memory_id,
                        _TEAM_A,
                        json.dumps(
                            [{**_lineup("changed")[0], "player_id": str(player_id)}]
                        ),
                    )
                )


def test_direct_token_rejects_numeric_uuid_and_normalizes_saved_payload(
    lineup_database: ProvisionedProductCatalog,
) -> None:
    """照合した選手 ID と保存 JSON の値型・識別値を一致させる。"""
    with lineup_database.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO players (tenant_id, id, team_record_id, name, "
            "roster_status_key) VALUES (%s, %s, %s, %s, 'active')",
            (_TENANT_A, _NUMERIC_PLAYER, _TEAM_A, "numeric-player"),
        )
    lineup_database.applicator.commit()
    numeric_lineup = json.dumps(
        [
            {
                "player_id": int(_NUMERIC_PLAYER.hex),
                "batting_order": 1,
                "fielding_position": "P",
            }
        ]
    )
    with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
        with pytest.raises(ValueError, match="UUID 文字列"):
            scope.run(_LineupMemoryInsertToken(uuid4(), _TEAM_A, numeric_lineup))

    extra_lineup = json.dumps([{**_lineup("P")[0], "untrusted": "ignored"}])
    with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
        scope.run(_LineupMemoryInsertToken(uuid4(), _TEAM_A, extra_lineup))
        saved = scope.run(LineupMemoryReadToken(_TEAM_A)).rows
    assert len(saved) == 1
    entries = saved[0][1]
    assert isinstance(entries, tuple)
    entry = entries[0]
    assert isinstance(entry, MappingProxyType)
    assert set(entry) == {"player_id", "batting_order", "fielding_position"}


def test_direct_token_rejects_mutable_json_before_validation(
    lineup_database: ProvisionedProductCatalog,
) -> None:
    """検証後に差し替えられる bytearray は両保存 token で拒否する。"""
    del lineup_database
    mutable_json = cast(str, bytearray(json.dumps(_lineup("P")).encode()))
    with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
        with pytest.raises(ValueError, match="不変な JSON 文字列"):
            scope.run(_LineupMemoryInsertToken(uuid4(), _TEAM_A, mutable_json))
        with pytest.raises(ValueError, match="不変な JSON 文字列"):
            scope.run(_LineupMemoryUpdateToken(uuid4(), _TEAM_A, mutable_json))


@pytest.mark.parametrize("kind", ("insert", "update"))
@pytest.mark.parametrize("executor", ("scope", "repository"))
def test_direct_token_mutation_after_preflight_cannot_change_saved_player(
    lineup_database: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    executor: str,
) -> None:
    """事前照合後の元 token 改変で未登録選手を保存させない。"""
    memory_id: UUID | None = None
    if kind == "update":
        with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
            save_lineup_memory(scope, _TEAM_A, _lineup("before"))
        with lineup_database.observer.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM lineup_memories WHERE tenant_id = %s "
                "AND team_record_id = %s AND retired_at IS NULL",
                (_TENANT_A, _TEAM_A),
            )
            row = cursor.fetchone()
        assert row is not None
        memory_id = row[0]

    token = _write_token(kind, memory_id, "checked")
    executor_module = transaction_module if executor == "scope" else base_module
    original_prepare = executor_module._prepare_operation
    tampered: list[bool] = []

    def mutate_original_after_write_prepared(
        operation: TenantOperationToken, tenant_id: UUID
    ) -> Any:
        if isinstance(operation, _SelfTeamLockToken) and not tampered:
            object.__setattr__(
                token,
                "lineup_json",
                json.dumps(
                    [{**_lineup("unchecked")[0], "player_id": str(_MISSING_PLAYER)}]
                ),
            )
            tampered.append(True)
        return original_prepare(operation, tenant_id)

    monkeypatch.setattr(
        executor_module, "_prepare_operation", mutate_original_after_write_prepared
    )
    if executor == "scope":
        with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
            scope.run(token)
    else:
        with Session(create_database_engine()) as session:
            _DirectLineupRepository(session).execute(
                make_tenant_context(_TENANT_A), token
            )

    assert tampered == [True]
    with lineup_database.observer.cursor() as cursor:
        cursor.execute(
            "SELECT lineup FROM lineup_memories WHERE tenant_id = %s "
            "AND team_record_id = %s AND retired_at IS NULL",
            (_TENANT_A, _TEAM_A),
        )
        rows = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == list(_lineup("checked"))


@pytest.mark.parametrize("kind", ("read", "insert", "update"))
@pytest.mark.parametrize("executor", ("scope", "repository"))
def test_in_place_uuid_mutation_after_preflight_cannot_change_target_team(
    lineup_database: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    executor: str,
) -> None:
    """照合後に元 UUID を内部変更しても相手チームへ向けられない。"""
    opponent_memory_id = uuid4()
    with lineup_database.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO team_records (tenant_id, id, kind, name) "
            "VALUES (%s, %s, 'opponent', %s)",
            (_TENANT_A, _OPPONENT_A, "opponent"),
        )
        if kind != "insert":
            cursor.execute(
                "INSERT INTO lineup_memories "
                "(tenant_id, id, team_record_id, lineup) VALUES (%s, %s, %s, %s)",
                (
                    _TENANT_A,
                    opponent_memory_id,
                    _OPPONENT_A,
                    json.dumps(_lineup("opponent-before")),
                ),
            )
    lineup_database.applicator.commit()
    if kind == "read":
        with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
            save_lineup_memory(scope, _TEAM_A, _lineup("self-before"))

    mutable_team_id = UUID(str(_TEAM_A))
    if kind == "read":
        operation: TenantOperationToken = LineupMemoryReadToken(mutable_team_id)
    elif kind == "insert":
        operation = _LineupMemoryInsertToken(
            uuid4(), mutable_team_id, json.dumps(_lineup("self-new"))
        )
    else:
        operation = _LineupMemoryUpdateToken(
            opponent_memory_id, mutable_team_id, json.dumps(_lineup("changed"))
        )

    executor_module = transaction_module if executor == "scope" else base_module
    original_materialize = executor_module._materialize_execution_result
    mutated: list[bool] = []

    def mutate_after_lock(statement: Any, execution_result: Any) -> Any:
        result = original_materialize(statement, execution_result)
        statement_text = str(statement)
        lock_table = "team_records" if kind == "read" else "players"
        if (
            f"FROM {lock_table}" in statement_text
            and "FOR UPDATE" in statement_text
            and not mutated
        ):
            object.__setattr__(mutable_team_id, "int", _OPPONENT_A.int)
            mutated.append(True)
        return result

    monkeypatch.setattr(
        executor_module, "_materialize_execution_result", mutate_after_lock
    )
    if executor == "scope":
        with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
            result = scope.run(operation)
    else:
        with Session(create_database_engine()) as session:
            result = _DirectLineupRepository(session).execute(
                make_tenant_context(_TENANT_A), operation
            )
    assert mutated == [True]

    if kind == "read":
        lineup = result.rows[0][1]
        assert isinstance(lineup, tuple)
        entry = lineup[0]
        assert isinstance(entry, MappingProxyType)
        assert entry["fielding_position"] == "self-before"
    else:
        with lineup_database.observer.cursor() as cursor:
            cursor.execute(
                "SELECT team_record_id, lineup FROM lineup_memories "
                "WHERE tenant_id = %s ORDER BY team_record_id",
                (_TENANT_A,),
            )
            rows = cursor.fetchall()
        if kind == "insert":
            assert rows == [(_TEAM_A, list(_lineup("self-new")))]
        else:
            assert result.rows == ((0,),)
            assert rows == [(_OPPONENT_A, list(_lineup("opponent-before")))]


def test_direct_read_token_cannot_read_opponent_memory(
    lineup_database: ProvisionedProductCatalog,
) -> None:
    """同一テナント内の相手チーム記憶も直接 token からは読ませない。"""
    with lineup_database.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO team_records (tenant_id, id, kind, name) "
            "VALUES (%s, %s, 'opponent', %s)",
            (_TENANT_A, _OPPONENT_A, "lineup-opponent"),
        )
        cursor.execute(
            "INSERT INTO lineup_memories (tenant_id, id, team_record_id, lineup) "
            "VALUES (%s, %s, %s, %s)",
            (_TENANT_A, uuid4(), _OPPONENT_A, json.dumps(_lineup("first"))),
        )
    lineup_database.applicator.commit()

    with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
        with pytest.raises(LineupMemoryUnavailable):
            scope.run(LineupMemoryReadToken(_OPPONENT_A))


def test_repository_execute_cannot_bypass_roster_checks(
    lineup_database: ProvisionedProductCatalog,
) -> None:
    """公開リポジトリ実行器でも直接 token の名簿検証を通す。"""
    del lineup_database
    invalid_lineup = json.dumps(
        [{**_lineup("first")[0], "player_id": str(_MISSING_PLAYER)}]
    )
    with Session(create_database_engine()) as session:
        repository = _DirectLineupRepository(session)
        with pytest.raises(LineupMemoryUnavailable):
            repository.execute(
                make_tenant_context(_TENANT_A),
                _LineupMemoryInsertToken(uuid4(), _TEAM_A, invalid_lineup),
            )


def test_repository_execute_rejects_opponent_read_and_update(
    lineup_database: ProvisionedProductCatalog,
) -> None:
    """公開実行器からも相手チームの記憶を読まず書き換えない。"""
    memory_id = uuid4()
    with lineup_database.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO team_records (tenant_id, id, kind, name) "
            "VALUES (%s, %s, 'opponent', %s)",
            (_TENANT_A, _OPPONENT_A, "lineup-opponent"),
        )
        cursor.execute(
            "INSERT INTO lineup_memories (tenant_id, id, team_record_id, lineup) "
            "VALUES (%s, %s, %s, %s)",
            (_TENANT_A, memory_id, _OPPONENT_A, json.dumps(_lineup("before"))),
        )
    lineup_database.applicator.commit()

    with Session(create_database_engine()) as session:
        repository = _DirectLineupRepository(session)
        with pytest.raises(LineupMemoryUnavailable):
            repository.execute(
                make_tenant_context(_TENANT_A), LineupMemoryReadToken(_OPPONENT_A)
            )
    with Session(create_database_engine()) as session:
        repository = _DirectLineupRepository(session)
        result = repository.execute(
            make_tenant_context(_TENANT_A),
            _LineupMemoryUpdateToken(memory_id, _TEAM_A, json.dumps(_lineup("after"))),
        )
        assert result.rows == ((0,),)


def test_repository_execute_checks_active_roster_for_update(
    lineup_database: ProvisionedProductCatalog,
) -> None:
    """公開実行器の正常更新と、非現役・削除・別チーム・別テナントを検証する。"""
    with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
        save_lineup_memory(scope, _TEAM_A, _lineup("before"))
        memory_id = scope.run(LineupMemoryReadToken(_TEAM_A)).rows[0][0]
    assert isinstance(memory_id, UUID)

    with Session(create_database_engine()) as session:
        result = _DirectLineupRepository(session).execute(
            make_tenant_context(_TENANT_A),
            _LineupMemoryUpdateToken(memory_id, _TEAM_A, json.dumps(_lineup("valid"))),
        )
        assert result.rows == ((1,),)

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

    for status, hidden, player_id, tenant_id in (
        ("ob", False, _PLAYER_A, _TENANT_A),
        ("active", True, _PLAYER_A, _TENANT_A),
        ("active", False, _OPPONENT_PLAYER_A, _TENANT_A),
        ("active", False, _PLAYER_A, _TENANT_B),
    ):
        with lineup_database.applicator.cursor() as cursor:
            cursor.execute(
                "UPDATE players SET roster_status_key = %s, hidden_at = "
                "CASE WHEN %s THEN now() ELSE NULL END "
                "WHERE tenant_id = %s AND id = %s",
                (status, hidden, _TENANT_A, _PLAYER_A),
            )
        lineup_database.applicator.commit()
        lineup_json = json.dumps(
            [{**_lineup("rejected")[0], "player_id": str(player_id)}]
        )
        with Session(create_database_engine()) as session:
            with pytest.raises(LineupMemoryUnavailable):
                _DirectLineupRepository(session).execute(
                    make_tenant_context(tenant_id),
                    _LineupMemoryUpdateToken(memory_id, _TEAM_A, lineup_json),
                )

    with lineup_database.observer.cursor() as cursor:
        cursor.execute(
            "SELECT lineup FROM lineup_memories WHERE tenant_id = %s AND id = %s",
            (_TENANT_A, memory_id),
        )
        row = cursor.fetchone()
    assert row is not None
    assert row[0][0]["fielding_position"] == "valid"


@pytest.mark.parametrize("target", ("opponent", "migration"))
def test_direct_update_cannot_change_opponent_or_migration_memory(
    lineup_database: ProvisionedProductCatalog,
    target: str,
) -> None:
    """有効な自チーム選手でも相手・移行由来の記憶は更新しない。"""
    opponent_memory_id = uuid4()
    migrated_memory_id = uuid4()
    original_lineup = json.dumps(_lineup("before"))
    changed_lineup = json.dumps(_lineup("after"))
    with lineup_database.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO team_records (tenant_id, id, kind, name) "
            "VALUES (%s, %s, 'opponent', %s)",
            (_TENANT_A, _OPPONENT_A, "lineup-opponent"),
        )
        cursor.execute(
            "INSERT INTO lineup_memories "
            "(tenant_id, id, team_record_id, lineup, migration_preserved_only) "
            "VALUES (%s, %s, %s, %s, false), (%s, %s, %s, %s, true)",
            (
                _TENANT_A,
                opponent_memory_id,
                _OPPONENT_A,
                original_lineup,
                _TENANT_A,
                migrated_memory_id,
                _TEAM_A,
                original_lineup,
            ),
        )
    lineup_database.applicator.commit()

    memory_id = opponent_memory_id if target == "opponent" else migrated_memory_id
    with tenant_transaction_scope(make_tenant_context(_TENANT_A)) as scope:
        try:
            result = scope.run(
                _LineupMemoryUpdateToken(memory_id, _TEAM_A, changed_lineup)
            )
        except LineupMemoryUnavailable:
            pass
        else:
            assert result.rows == ((0,),)

    with lineup_database.observer.cursor() as cursor:
        cursor.execute(
            "SELECT id, lineup FROM lineup_memories WHERE tenant_id = %s "
            "AND id IN (%s, %s)",
            (_TENANT_A, opponent_memory_id, migrated_memory_id),
        )
        rows: list[tuple[Any, ...]] = cursor.fetchall()
    assert len(rows) == 2
    assert all(row[1][0]["fielding_position"] == "before" for row in rows)
