"""P2 の直列化・局所再採番・O4 を使い捨て製品 DB で検査する。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event, current_thread
from uuid import UUID, uuid4

import pytest
from test_authz_tenant_context import make_tenant_context
from test_sync_apply_port_prefix import (
    FailingPrefixProjection,
    PrefixProjection,
    PrefixRights,
    PrefixValidator,
)

from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync import ordering, ports
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ordering import apply_p2_event
from pitchlog.sync.prefix_path import P1Result
from pitchlog.sync.tokens import GameLockToken

from .test_sync_apply_operations_boundary import _SyncDatabase, sync_database
from .test_sync_apply_prefix_path_boundary import prefix_database

__all__ = ("sync_database", "prefix_database")

pytestmark = pytest.mark.requires_db


@pytest.fixture(autouse=True)
def _register_ordering_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    """製品の空登録表は変えず、合成ポートだけをこの試験で許す。"""
    monkeypatch.setattr(
        ports,
        "PORT_IMPLEMENTATIONS",
        frozenset(
            (cls.__module__, cls.__name__)
            for cls in (
                PrefixRights,
                PrefixProjection,
                FailingPrefixProjection,
                PrefixValidator,
            )
        ),
    )


def _event(game_id: UUID, d1: int, d2: int) -> SyncEvent:
    """D2 に参加する新規の P2 イベントを作る。"""
    return SyncEvent(
        str(uuid4()),
        str(game_id),
        d1,
        "epoch",
        v5="play_input",
        v6=d2,
        v7={},
        v8={},
    )


def _apply(
    db: _SyncDatabase,
    event: SyncEvent,
    projection: PrefixProjection | FailingPrefixProjection | None = None,
) -> tuple[P1Result, PrefixProjection | FailingPrefixProjection]:
    """同じ使い捨て DB の自テナント文脈で P2 を適用する。"""
    selected = projection or PrefixProjection()
    outcome = apply_p2_event(
        make_tenant_context(db.tenant_a),
        event,
        PrefixRights(),
        selected,
        PrefixValidator(),
        "proof",
    )
    return outcome, selected


def _rows(db: _SyncDatabase) -> list[tuple[int, int]]:
    """試合の受理済み D1・D2 を独立した SQL で読む。"""
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT d1, d2 FROM operation_events WHERE tenant_id = %s "
            "AND game_id = %s ORDER BY d1",
            (db.tenant_a, db.game_a),
        )
        result = cursor.fetchall()
    db.catalog.applicator.rollback()
    return [(int(d1), int(d2)) for d1, d2 in result]


def _watermark(db: _SyncDatabase) -> int:
    """D3 をアプリの戻り値とは独立に観測する。"""
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT confirmed_watermark FROM recording_generations "
            "WHERE tenant_id = %s AND game_id = %s AND generation = 1",
            (db.tenant_a, db.game_a),
        )
        row = cursor.fetchone()
    db.catalog.applicator.rollback()
    assert row is not None
    return int(row[0])


def test_same_game_transactions_never_commit_equal_d2(
    prefix_database: _SyncDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O1: 先着が試合行ロックを保持した間に後着を開始する。"""
    db = prefix_database
    first_at_t5 = Event()
    second_on_game_lock = Event()
    release_first = Event()
    original = ordering._assign_d2
    original_run = _TenantTransaction.run

    def observe_lock(
        scope: _TenantTransaction, operation: TenantOperationToken
    ) -> TenantOperationResult:
        """後着が実際に試合行の行ロックを要求した時点を知らせる。"""
        if type(operation) is GameLockToken and current_thread().name == "p2_1":
            second_on_game_lock.set()
        return original_run(scope, operation)

    monkeypatch.setattr(_TenantTransaction, "run", observe_lock)

    def pause_first(
        scope: _TenantTransaction, game_id: UUID, desired: int
    ) -> int | None:
        """T5 への到達を注入点とし、先着のロック保持を固定する。"""
        if desired == 10 and not first_at_t5.is_set():
            first_at_t5.set()
            if not release_first.wait(30):
                raise AssertionError("先着の解放が届かない")
        return original(scope, game_id, desired)

    monkeypatch.setattr(ordering, "_assign_d2", pause_first)
    first = _event(db.game_a, 1, 10)
    second = _event(db.game_a, 2, 10)

    def apply_second() -> P1Result:
        """先着のロック保持中に後着のトランザクションを開始する。"""
        return _apply(db, second)[0]

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="p2") as pool:
        first_future = pool.submit(_apply, db, first)
        try:
            assert first_at_t5.wait(30)
            second_future = pool.submit(apply_second)
            assert second_on_game_lock.wait(30)
        finally:
            release_first.set()
        first_result = first_future.result(timeout=60)[0]
        second_result = second_future.result(timeout=60)
    assert first_result.accepted and second_result.accepted
    assert _rows(db) == [(1, 10), (2, 9)]
    assert _watermark(db) == 2


def test_gap_exhaustion_renumber_and_insert_are_atomic(
    prefix_database: _SyncDatabase,
) -> None:
    """O2: 投影失敗では移動も挿入も戻し、成功時だけ一緒に確定する。"""
    db = prefix_database
    for d1, d2 in ((1, 9), (2, 10), (3, 11)):
        outcome, _ = _apply(db, _event(db.game_a, d1, d2))
        assert outcome.accepted
    assert _rows(db) == [(1, 9), (2, 10), (3, 11)]

    fourth = _event(db.game_a, 4, 10)
    with pytest.raises(RuntimeError, match="合成投影失敗"):
        _apply(db, fourth, FailingPrefixProjection())
    assert _rows(db) == [(1, 9), (2, 10), (3, 11)]
    assert _watermark(db) == 3

    outcome, projection = _apply(db, fourth)
    assert outcome.accepted and outcome.d3 == 4
    assert len(projection.events) == 1
    assert _rows(db) == [(1, 9), (2, 11), (3, 12), (4, 10)]
    replay, later_projection = _apply(db, fourth)
    assert replay.replayed
    assert later_projection.events == []
    assert _rows(db) == [(1, 9), (2, 11), (3, 12), (4, 10)]


def test_reused_d5_with_different_v5_is_b3b_before_kind_check(
    prefix_database: _SyncDatabase,
) -> None:
    """受理済み D5 の V5 だけを変えた再送は B3b 候補となる。"""
    db = prefix_database
    original = _event(db.game_a, 1, 10)
    assert _apply(db, original)[0].accepted
    changed = SyncEvent(
        original.d5,
        original.game_id,
        original.d1,
        original.d4,
        v5="player_registration",
        v7={},
    )
    result, projection = _apply(db, changed)
    assert result.boundary == "B3b"
    assert not result.accepted
    assert projection.events == []
    assert _rows(db) == [(1, 10)]
    assert _watermark(db) == 1


def test_reused_d5_with_malformed_v9_is_b3b_before_shape_check(
    prefix_database: _SyncDatabase,
) -> None:
    """受理済み D5 の V9 を壊した再送も先に B3b へ分類する。"""
    db = prefix_database
    original = _event(db.game_a, 1, 10)
    assert _apply(db, original)[0].accepted
    changed = SyncEvent(
        original.d5,
        original.game_id,
        original.d1,
        original.d4,
        v5=original.v5,
        v6=original.v6,
        v7=original.v7,
        v8=original.v8,
        v9={"tombstone": False},
    )
    result, projection = _apply(db, changed)
    assert result.boundary == "B3b"
    assert not result.accepted
    assert projection.events == []
    assert _rows(db) == [(1, 10)]
    assert _watermark(db) == 1


def test_bigint_limit_renumbers_left_and_persists_new_d2(
    prefix_database: _SyncDatabase,
) -> None:
    """上限の衝突では左の既存行だけを動かし、新イベントも同時に保存する。"""
    db = prefix_database
    maximum = ordering._MAX_D2
    for d1, d2 in ((1, maximum - 1), (2, maximum)):
        assert _apply(db, _event(db.game_a, d1, d2))[0].accepted
    assert _rows(db) == [(1, maximum - 1), (2, maximum)]

    result, projection = _apply(db, _event(db.game_a, 3, maximum))
    assert result.accepted and result.d3 == 3
    assert len(projection.events) == 1 and projection.events[0].v6 == maximum - 1
    assert _rows(db) == [(1, maximum - 2), (2, maximum), (3, maximum - 1)]
    assert _watermark(db) == 3


def test_persisted_equal_d2_returns_b3_and_rejects_without_projection(
    prefix_database: _SyncDatabase,
) -> None:
    """O4: 壊れた永続データでは D3 を進めず、投影も呼ばない。"""
    db = prefix_database
    for d1, d2 in ((1, 10), (2, 11)):
        assert _apply(db, _event(db.game_a, d1, d2))[0].accepted
    # 部分一意索引の欠落を使い捨て DB 内だけで再現する。
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute("DROP INDEX uq_operation_events_active_d2")
        cursor.execute(
            "UPDATE operation_events SET d2 = 10 WHERE tenant_id = %s "
            "AND game_id = %s AND d1 = 2",
            (db.tenant_a, db.game_a),
        )
    db.catalog.applicator.commit()
    try:
        projection = PrefixProjection()
        result, _ = _apply(db, _event(db.game_a, 3, 20), projection)
        assert result.boundary == "B3"
        assert result.a5 == "拒否"
        assert result.reason is not None and "O4" in result.reason
        assert not result.accepted
        assert projection.events == []
        assert _rows(db) == [(1, 10), (2, 10)]
        assert _watermark(db) == 2
    finally:
        # 外部供給の使い捨てカタログが次の試験にも使われる場合に索引を戻す。
        with db.catalog.applicator.cursor() as cursor:
            cursor.execute(
                "UPDATE operation_events SET d2 = 11 WHERE tenant_id = %s "
                "AND game_id = %s AND d1 = 2",
                (db.tenant_a, db.game_a),
            )
            cursor.execute(
                "CREATE UNIQUE INDEX uq_operation_events_active_d2 "
                "ON operation_events (tenant_id, game_id, d2) "
                "WHERE d2 IS NOT NULL AND replaced_at IS NULL "
                "AND retired_at IS NULL"
            )
        db.catalog.applicator.commit()
