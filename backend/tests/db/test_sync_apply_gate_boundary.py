"""RG1 のコミット前失敗が同期イベントの全書き込みを戻すことを調べる。"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from test_authz_tenant_context import make_tenant_context
from test_sync_apply_port_change import ChangeProjection, ChangeRights, ChangeValidator
from test_sync_apply_port_prefix import PrefixProjection, PrefixRights, PrefixValidator

from pitchlog.sync import ports
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.prefix_path import apply_p1_event

from .test_sync_apply_operations_boundary import _SyncDatabase, sync_database
from .test_sync_apply_prefix_path_boundary import prefix_database

__all__ = ("prefix_database", "sync_database")

pytestmark = pytest.mark.requires_db


@pytest.fixture(autouse=True)
def _register_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    """本物の登録表を変えず、合成ポートだけを接続する。"""
    monkeypatch.setattr(
        ports,
        "PORT_IMPLEMENTATIONS",
        frozenset(
            (cls.__module__, cls.__name__)
            for cls in (
                PrefixRights,
                PrefixProjection,
                PrefixValidator,
                ChangeRights,
                ChangeProjection,
                ChangeValidator,
            )
        ),
    )


def _remaining(db: _SyncDatabase, d5: UUID) -> tuple[int, int, int, int]:
    """P1 が書く台帳・スロット・イベント・意図を独立に数える。"""
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM idempotency_ledger WHERE tenant_id = %s AND d5 = %s",
            (db.tenant_a, d5),
        )
        ledger = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) FROM event_slots WHERE tenant_id = %s AND game_id = %s",
            (db.tenant_a, db.game_a),
        )
        slots = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) FROM operation_events WHERE tenant_id = %s AND d5 = %s",
            (db.tenant_a, d5),
        )
        events = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) FROM invalidation_intents WHERE tenant_id = %s "
            "AND intent_id LIKE %s",
            (db.tenant_a, f"sync:{d5}:%"),
        )
        intents = cursor.fetchone()
    assert ledger is not None and slots is not None
    assert events is not None and intents is not None
    return ledger[0], slots[0], events[0], intents[0]


@pytest.mark.parametrize("failure", ["closed", "error"])
def test_p1_rg1_commit_failure_rolls_back_every_t_element(
    prefix_database: _SyncDatabase, failure: str
) -> None:
    """台帳・スロット・イベント・範囲別意図は⑧の失敗で一緒に戻る。"""
    db = prefix_database
    d5 = uuid4()
    event = SyncEvent(
        str(d5),
        str(db.game_a),
        1,
        "epoch",
        v5="game_end_declaration",
        v6=10,
        v7={},
    )
    rights = PrefixRights(
        commit_open=failure != "closed",
        fail_at="commit" if failure == "error" else None,
    )
    result = apply_p1_event(
        make_tenant_context(db.tenant_a),
        event,
        rights,
        PrefixProjection(),
        PrefixValidator(),
        "proof",
    )
    assert result.boundary == "B7"
    assert rights.rg1_calls == ["read", "commit"]
    assert _remaining(db, d5) == (0, 0, 0, 0)


def test_p1_replay_checks_rg1_before_reading_saved_d5(
    prefix_database: _SyncDatabase,
) -> None:
    """保存済み結果も③-a の閉鎖中は再掲せず、B7 で止まる。"""
    db = prefix_database
    d5 = uuid4()
    event = SyncEvent(
        str(d5),
        str(db.game_a),
        1,
        "epoch",
        v5="game_end_declaration",
        v6=10,
        v7={},
    )
    context = make_tenant_context(db.tenant_a)
    first = apply_p1_event(
        context, event, PrefixRights(), PrefixProjection(), PrefixValidator(), "proof"
    )
    assert first.accepted
    closed = PrefixRights(read_open=False)
    replay = apply_p1_event(
        context, event, closed, PrefixProjection(), PrefixValidator(), "proof"
    )
    assert replay.boundary == "B7"
    assert closed.rg1_calls == ["read"]
    assert _remaining(db, d5) == (1, 1, 1, 5)


def test_p1_other_tenant_and_missing_game_stop_before_rg1(
    prefix_database: _SyncDatabase,
) -> None:
    """B6 も不存在と他テナントを区別せず、閉じた RG1 へ到達しない。"""
    db = prefix_database
    d5 = uuid4()
    results = []
    for game_id in (db.game_b, uuid4()):
        rights = PrefixRights(read_open=False)
        event = SyncEvent(
            str(d5),
            str(game_id),
            1,
            "epoch",
            v5="game_end_declaration",
            v6=10,
            v7={},
        )
        result = apply_p1_event(
            make_tenant_context(db.tenant_a),
            event,
            rights,
            PrefixProjection(),
            PrefixValidator(),
            "proof",
        )
        results.append(result)
        assert rights.rg1_calls == []
    assert results[0] == results[1]
    assert results[0].boundary == "B6"
    assert _remaining(db, d5) == (0, 0, 0, 0)
