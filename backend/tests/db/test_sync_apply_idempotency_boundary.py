"""D5 のテナント境界と順序を固定した競合を使い捨て DB で検査する。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Event
from typing import cast
from uuid import UUID, uuid4

import pytest
from test_authz_tenant_context import make_tenant_context

from pitchlog.repositories.transaction import (
    _TenantTransaction,
    tenant_transaction_scope,
)
from pitchlog.sync.idempotency import (
    D5Candidate,
    classify_d5,
    recheck_and_insert_result,
)
from pitchlog.sync.tokens import (
    GameLockToken,
    GameReadToken,
    IdempotencyLedgerInsertToken,
    RecordingGenerationLockToken,
)

from .test_sync_apply_operations_boundary import _SyncDatabase

pytestmark = pytest.mark.requires_db
pytest_plugins = ("db.test_sync_apply_operations_boundary",)


@dataclass(frozen=True, slots=True)
class _TwoGames:
    """同じテナントの異なる試合行を保持する。"""

    database: _SyncDatabase
    second_game: UUID


@pytest.fixture
def two_games(sync_database: _SyncDatabase) -> _TwoGames:
    """先着と後着が別々にロックできる試合・世代行を作る。"""
    game_id = uuid4()
    with sync_database.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO games (tenant_id, id, scheduled_at, game_type_key, "
            "tournament_key, away_team_record_id, home_team_record_id, applied_rules) "
            "SELECT tenant_id, %s, scheduled_at, game_type_key, tournament_key, "
            "away_team_record_id, home_team_record_id, applied_rules FROM games "
            "WHERE tenant_id = %s AND id = %s",
            (game_id, sync_database.tenant_a, sync_database.game_a),
        )
        cursor.execute(
            "INSERT INTO recording_generations (tenant_id, game_id, generation, "
            "kind, issuance_order, holder_device) "
            "VALUES (%s, %s, 1, 'normal', 1, 'test-device')",
            (sync_database.tenant_a, game_id),
        )
    sync_database.catalog.applicator.commit()
    return _TwoGames(sync_database, game_id)


def _token(d5: UUID, fingerprint: str) -> IdempotencyLedgerInsertToken:
    """確定結果を D5 と同じ INSERT に含める。"""
    return IdempotencyLedgerInsertToken(d5, "accepted", fingerprint, '{"state":"受理"}')


def _lock_game_and_generation(scope: _TenantTransaction, game_id: UUID) -> None:
    """R-16 の共通順で、試合行から記録権世代行をロックする。"""
    assert len(scope.run(GameLockToken(game_id)).rows) == 1
    assert len(scope.run(RecordingGenerationLockToken(game_id, 1)).rows) == 1


def test_three_candidates_and_other_tenant_same_d5_are_indistinguishable(
    sync_database: _SyncDatabase,
) -> None:
    """保存結果・衝突・未使用を実 DB で読み、他テナントの存在を漏らさない。"""
    d5, unused = uuid4(), uuid4()
    db = sync_database
    with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
        assert classify_d5(scope, d5, "original", "P1").kind == "unused"
        assert recheck_and_insert_result(scope, _token(d5, "original"), "P1") is None
        replay = classify_d5(scope, d5, "original", "P1")
        assert replay.kind == "stored_result"
        assert replay.stored is not None
        assert replay.stored.result["state"] == "受理"
        assert classify_d5(scope, d5, "changed", "P1").boundary == "B3b"
        assert classify_d5(scope, d5, "changed", "P3").boundary == "B13"
        assert classify_d5(scope, unused, "original", "P1").kind == "unused"

    with tenant_transaction_scope(make_tenant_context(db.tenant_b)) as scope:
        # 他テナントに同じ D5 が存在することは未使用 D5 と同じ結果になる。
        assert classify_d5(scope, d5, "original", "P1") == classify_d5(
            scope, unused, "original", "P1"
        )
        assert recheck_and_insert_result(scope, _token(d5, "other"), "P1") is None
        assert classify_d5(scope, d5, "other", "P1").kind == "stored_result"

    with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
        assert classify_d5(scope, d5, "original", "P1").kind == "stored_result"


@pytest.mark.parametrize("same_content", [True, False])
def test_recheck_after_both_classified_unused(
    two_games: _TwoGames, same_content: bool
) -> None:
    """先着確定後に後着を再開し、INSERT 前の再照合で再掲か B3b にする。"""
    db = two_games.database
    d5 = uuid4()
    first_classified, second_classified, first_committed = Event(), Event(), Event()
    later = "same" if same_content else "different"

    def first() -> None:
        with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
            _lock_game_and_generation(scope, db.game_a)
            assert classify_d5(scope, d5, "same", "P1").kind == "unused"
            first_classified.set()
            assert second_classified.wait(30)
            assert recheck_and_insert_result(scope, _token(d5, "same"), "P1") is None
        first_committed.set()

    def second() -> D5Candidate | None:
        assert first_classified.wait(30)
        with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
            _lock_game_and_generation(scope, two_games.second_game)
            assert classify_d5(scope, d5, later, "P1").kind == "unused"
            second_classified.set()
            assert first_committed.wait(30)
            candidate = recheck_and_insert_result(scope, _token(d5, later), "P1")
            assert len(scope.run(GameReadToken(two_games.second_game)).rows) == 1
            return candidate

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(first)
        second_future = pool.submit(second)
        first_future.result(timeout=40)
        candidate = second_future.result(timeout=40)
    assert candidate is not None
    assert candidate.kind == ("stored_result" if same_content else "conflict")
    assert candidate.boundary == (None if same_content else "B3b")


class _BeforeInsertHandle:
    """テスト側だけで、後着の再照合後・INSERT 直前に待機させる。"""

    def __init__(
        self, real: _TenantTransaction, ready: Event, committed: Event
    ) -> None:
        self.real = real
        self.ready = ready
        self.committed = committed

    def run(self, operation: object) -> object:
        """読み取り operation を実ハンドルへ渡す。"""
        from pitchlog.repositories.tokens import TenantOperationToken

        return self.real.run(cast(TenantOperationToken, operation))

    def run_in_savepoint(self, operation: object) -> object:
        """再照合後の停止点を通知してから INSERT を実行する。"""
        from pitchlog.repositories.tokens import TenantOperationToken

        self.ready.set()
        assert self.committed.wait(30)
        return self.real.run_in_savepoint(cast(TenantOperationToken, operation))


@pytest.mark.parametrize("same_content", [True, False])
def test_unique_race_rolls_back_savepoint_and_keeps_outer_transaction(
    two_games: _TwoGames, same_content: bool
) -> None:
    """後着が INSERT 直前で止まり、先着確定後の一意衝突だけを戻す。"""
    db = two_games.database
    d5 = uuid4()
    second_ready, first_committed = Event(), Event()
    later = "same" if same_content else "different"

    def second() -> D5Candidate | None:
        with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
            _lock_game_and_generation(scope, two_games.second_game)
            handle = cast(
                _TenantTransaction,
                _BeforeInsertHandle(scope, second_ready, first_committed),
            )
            candidate = recheck_and_insert_result(handle, _token(d5, later), "P1")
            # 一意違反後にも親トランザクションは読み書き可能な状態を保つ。
            assert len(scope.run(GameReadToken(two_games.second_game)).rows) == 1
            return candidate

    def first() -> None:
        assert second_ready.wait(30)
        with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
            _lock_game_and_generation(scope, db.game_a)
            assert recheck_and_insert_result(scope, _token(d5, "same"), "P1") is None
        first_committed.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        second_future = pool.submit(second)
        first_future = pool.submit(first)
        first_future.result(timeout=40)
        candidate = second_future.result(timeout=40)
    assert candidate is not None
    assert candidate.kind == ("stored_result" if same_content else "conflict")
    assert candidate.boundary == (None if same_content else "B3b")

    with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
        assert classify_d5(scope, d5, "same", "P1").kind == "stored_result"
