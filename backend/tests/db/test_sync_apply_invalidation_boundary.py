"""同期経路の五つの意図行を使い捨て製品 DB で確認する。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from test_authz_tenant_context import make_tenant_context

from pitchlog.repositories.invalidation_intents import SCOPE_KIND_BY_SCOPE
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.repositories.transaction import (
    _TenantTransaction,
    tenant_transaction_scope,
)
from pitchlog.sync.invalidation import record_d1_intents, record_p3_intents
from pitchlog.sync.tokens import InvalidationIntentReadToken

from .test_sync_apply_operations_boundary import _SyncDatabase, sync_database

__all__ = ("sync_database",)

pytestmark = pytest.mark.requires_db
_EXPECTED_SCOPE_KINDS = (
    "game",
    "player_total",
    "team_total",
    "shared_total",
    "chart",
)


@pytest.mark.parametrize("path", ["P3", "D1"])
def test_sync_intents_are_five_scope_rows_and_replay_is_idempotent(
    sync_database: _SyncDatabase,
    path: str,
) -> None:
    """P3 と D1 の各入力が同一トランザクションで五行になり再掲で増えない。"""
    db = sync_database
    d5 = uuid4()

    def record() -> tuple[str, ...]:
        with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
            if path == "P3":
                return record_p3_intents(scope, db.game_a, 1, 1, 2)
            return record_d1_intents(scope, db.game_a, d5)

    expected_identity = f"{db.game_a}:1:1:2" if path == "P3" else str(d5)
    expected = tuple(
        f"sync:{expected_identity}:{kind}" for kind in _EXPECTED_SCOPE_KINDS
    )
    assert tuple(SCOPE_KIND_BY_SCOPE.values()) == _EXPECTED_SCOPE_KINDS
    assert record() == expected
    assert record() == expected
    assert len(set(expected)) == 5  # 範囲だけを変えると ID が変わる。

    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT intent_id, scope_kind, game_id, target_tenant_id, "
            "delivery_status FROM invalidation_intents WHERE tenant_id = %s",
            (db.tenant_a,),
        )
        rows = cursor.fetchall()
    db.catalog.applicator.rollback()
    assert len(rows) == 5
    assert {row[0] for row in rows} == set(expected)
    assert {row[1] for row in rows} == set(_EXPECTED_SCOPE_KINDS)
    assert all(row[4] == "pending" for row in rows)
    for _, kind, game_id, target_tenant_id, _ in rows:
        assert game_id == (db.game_a if kind == "game" else None)
        assert target_tenant_id == (db.tenant_a if kind == "shared_total" else None)

    # 元の五行を確認した後、確定版または D5 だけを変えて別 ID を記録する。
    with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
        if path == "P3":
            changed = record_p3_intents(scope, db.game_a, 1, 1, 3)
            changed_identity = f"{db.game_a}:1:1:3"
        else:
            changed_d5 = uuid4()
            changed = record_d1_intents(scope, db.game_a, changed_d5)
            changed_identity = str(changed_d5)
    assert changed == tuple(
        f"sync:{changed_identity}:{kind}" for kind in _EXPECTED_SCOPE_KINDS
    )
    assert set(expected).isdisjoint(changed)


class _ConcurrentIntentHandle:
    """最初の不在読み取り後に二つのトランザクションを整列させる。"""

    def __init__(
        self,
        real: _TenantTransaction,
        first_intent_id: str,
        read_done: Event,
        may_continue: Event,
    ) -> None:
        """実ハンドルとテスト専用の停止点を保持する。"""
        self.real = real
        self.first_intent_id = first_intent_id
        self.read_done = read_done
        self.may_continue = may_continue
        self.paused = False
        self.primary_key_collisions = 0

    def run(self, operation: TenantOperationToken) -> TenantOperationResult:
        """初回の不在読取を通知し、相手の確定まで待つ。"""
        result = self.real.run(operation)
        if (
            isinstance(operation, InvalidationIntentReadToken)
            and operation.intent_id == self.first_intent_id
            and not result.rows
            and not self.paused
        ):
            self.paused = True
            self.read_done.set()
            assert self.may_continue.wait(30)
        return result

    def run_in_savepoint(
        self, operation: TenantOperationToken
    ) -> TenantOperationResult:
        """意図の主キー衝突が実際に起きた回数を記録する。"""
        try:
            return self.real.run_in_savepoint(operation)
        except IntegrityError as error:
            diagnostic = getattr(error.orig, "diag", None)
            if (
                getattr(diagnostic, "constraint_name", None)
                == "pk_invalidation_intents"
            ):
                self.primary_key_collisions += 1
            raise


def test_same_intent_concurrent_insert_recovers_after_savepoint(
    sync_database: _SyncDatabase,
) -> None:
    """両者が不在を読んだ後の主キー競合でも後着の親取引を継続する。"""
    db = sync_database
    d5 = uuid4()
    expected = tuple(f"sync:{d5}:{kind}" for kind in _EXPECTED_SCOPE_KINDS)
    first_read, second_read, first_committed = Event(), Event(), Event()

    def first() -> tuple[str, ...]:
        with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
            handle = _ConcurrentIntentHandle(
                scope, expected[0], first_read, second_read
            )
            recorded = record_d1_intents(
                cast(_TenantTransaction, handle), db.game_a, d5
            )
        first_committed.set()
        return recorded

    def second() -> tuple[tuple[str, ...], int]:
        assert first_read.wait(30)
        with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
            handle = _ConcurrentIntentHandle(
                scope, expected[0], second_read, first_committed
            )
            recorded = record_d1_intents(
                cast(_TenantTransaction, handle), db.game_a, d5
            )
            # SAVEPOINT の外にある親取引でも読取を継続できる。
            assert scope.run(InvalidationIntentReadToken(expected[0])).rows
            return recorded, handle.primary_key_collisions

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(first)
        second_future = pool.submit(second)
        assert first_future.result(timeout=40) == expected
        second_recorded, collisions = second_future.result(timeout=40)
    assert second_recorded == expected
    assert collisions == 1

    with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
        assert all(
            scope.run(InvalidationIntentReadToken(intent_id)).rows
            for intent_id in expected
        )
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT intent_id FROM invalidation_intents WHERE tenant_id = %s",
            (db.tenant_a,),
        )
        persisted = cursor.fetchall()
    db.catalog.applicator.rollback()
    assert {row[0] for row in persisted} == set(expected)
    assert len(persisted) == 5
