"""P5/T9 と P4/T8 の原子的な保存を使い捨て製品 DB で確かめる。"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from psycopg import sql
from test_authz_tenant_context import make_tenant_context
from test_sync_apply_port_prefix import (
    DenyPrefixRights,
    PrefixProjection,
    PrefixRights,
    PrefixValidator,
)

from pitchlog.sync import ports, rejection
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.prefix_path import apply_p1_event
from pitchlog.sync.rejection import apply_rejection_or_escrow

from .test_sync_apply_operations_boundary import _SyncDatabase

pytestmark = pytest.mark.requires_db
pytest_plugins = ("db.test_sync_apply_operations_boundary",)


@pytest.fixture(autouse=True)
def _register_rights(monkeypatch: pytest.MonkeyPatch) -> None:
    """テスト中だけ合成ポートを登録する。"""
    monkeypatch.setattr(
        ports,
        "PORT_IMPLEMENTATIONS",
        frozenset(
            (cls.__module__, cls.__name__) for cls in (PrefixRights, DenyPrefixRights)
        ),
    )


def _event(
    game_id: UUID, *, d5: UUID | None = None, changed: bool = False
) -> SyncEvent:
    """D1 付き種別の V 条件を満たすイベント原本を作る。"""
    return SyncEvent(
        str(d5 or uuid4()),
        str(game_id),
        1,
        "1",
        v5="game_end_declaration",
        v6=10,
        v7={"changed": changed},
    )


def _counts(db: _SyncDatabase, d5: UUID) -> tuple[int, int, int, int]:
    """台帳・拒否原本・退避原本・操作イベントを独立 SQL で数える。"""
    with db.catalog.applicator.cursor() as cursor:
        totals: list[int] = []
        for table in (
            "idempotency_ledger",
            "rejected_event_originals",
            "evacuated_event_originals",
            "operation_events",
        ):
            cursor.execute(
                sql.SQL(
                    "SELECT count(*) FROM {} WHERE tenant_id = %s AND d5 = %s"
                ).format(sql.Identifier(table)),
                (db.tenant_a, d5),
            )
            row = cursor.fetchone()
            assert row is not None
            totals.append(row[0])
    return totals[0], totals[1], totals[2], totals[3]


def _watermark(db: _SyncDatabase) -> int:
    """拒否・退避が D3 を進めなかったことを DB の行で確認する。"""
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT confirmed_watermark FROM recording_generations "
            "WHERE tenant_id = %s AND game_id = %s AND generation = 1",
            (db.tenant_a, db.game_a),
        )
        row = cursor.fetchone()
        assert row is not None
        return row[0]


def test_b3a_replay_and_b3b_do_not_add_originals(
    sync_database: _SyncDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T9 の拒否理由を再掲し、異内容 B3b では台帳も原本も変えない。"""
    db = sync_database
    event = _event(db.game_a)
    rights = PrefixRights()
    first = apply_rejection_or_escrow(
        make_tenant_context(db.tenant_a),
        event,
        rights,
        "proof",
        path="P1",
        reason="内容の意味が不正",
    )
    assert (first.boundary, first.state, first.d3, first.reason) == (
        "B3a",
        "拒否",
        0,
        "内容の意味が不正",
    )
    assert _counts(db, UUID(event.d5)) == (1, 1, 0, 0)
    assert _watermark(db) == 0

    replay_rights = DenyPrefixRights()
    replay = apply_rejection_or_escrow(
        make_tenant_context(db.tenant_a),
        event,
        replay_rights,
        "new-proof",
        path="P1",
        reason="後から変わった理由",
    )
    assert replay == first.__class__("B3a", 0, "拒否", "内容の意味が不正", True)
    assert replay_rights.calls == []
    projection = PrefixProjection()
    validator = PrefixValidator()
    common_replay = apply_p1_event(
        make_tenant_context(db.tenant_a),
        event,
        replay_rights,
        projection,
        validator,
        "new-proof",
    )
    assert (
        common_replay.boundary,
        common_replay.a5,
        common_replay.reason,
        common_replay.replayed,
    ) == ("B3a", "拒否", "内容の意味が不正", True)
    assert replay_rights.calls == []
    assert projection.events == []
    assert validator.calls == []

    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT source_fingerprint, result, reason FROM idempotency_ledger "
            "WHERE tenant_id = %s AND d5 = %s",
            (db.tenant_a, UUID(event.d5)),
        )
        ledger_before = cursor.fetchone()
        cursor.execute(
            "SELECT payload FROM rejected_event_originals "
            "WHERE tenant_id = %s AND d5 = %s",
            (db.tenant_a, UUID(event.d5)),
        )
        original_before = cursor.fetchone()

    changed = _event(db.game_a, d5=UUID(event.d5), changed=True)
    with monkeypatch.context() as mutation:
        mutation.setattr(
            rejection,
            "recheck_and_insert_result",
            lambda *args: pytest.fail("B3b で T9 を開始した"),
        )
        conflict = apply_rejection_or_escrow(
            make_tenant_context(db.tenant_a),
            changed,
            DenyPrefixRights(),
            "proof",
            path="P1",
            reason="別の内容",
        )
    assert conflict.boundary == "B3b"
    assert _counts(db, UUID(event.d5)) == (1, 1, 0, 0)
    assert _watermark(db) == 0
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT source_fingerprint, result, reason FROM idempotency_ledger "
            "WHERE tenant_id = %s AND d5 = %s",
            (db.tenant_a, UUID(event.d5)),
        )
        assert cursor.fetchone() == ledger_before
        cursor.execute(
            "SELECT payload FROM rejected_event_originals "
            "WHERE tenant_id = %s AND d5 = %s",
            (db.tenant_a, UUID(event.d5)),
        )
        assert cursor.fetchone() == original_before


def test_b4_persists_original_before_result_and_replays_without_current_rights(
    sync_database: _SyncDatabase,
) -> None:
    """退避原本と A5 退避を一体で保存し、後日の記録権を参照しない。"""
    db = sync_database
    event = _event(db.game_a)
    first = apply_rejection_or_escrow(
        make_tenant_context(db.tenant_a),
        event,
        DenyPrefixRights(),
        "expired-proof",
        path="P4",
        reason=None,
    )
    assert (first.boundary, first.state, first.d3) == ("B4", "退避", 0)
    assert _counts(db, UUID(event.d5)) == (1, 0, 1, 0)
    assert _watermark(db) == 0
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT kind, result FROM idempotency_ledger "
            "WHERE tenant_id = %s AND d5 = %s",
            (db.tenant_a, UUID(event.d5)),
        )
        assert cursor.fetchone() == ("evacuated", {"state": "退避", "d3": 0})
        cursor.execute(
            "SELECT origin, old_generation, original_d1 FROM "
            "evacuated_event_originals WHERE tenant_id = %s AND d5 = %s",
            (db.tenant_a, UUID(event.d5)),
        )
        assert cursor.fetchone() == ("authority_mismatch", 1, 1)

    rights_now = PrefixRights()
    replay = apply_rejection_or_escrow(
        make_tenant_context(db.tenant_a),
        event,
        rights_now,
        "valid-proof",
        path="P4",
        reason=None,
    )
    assert (replay.boundary, replay.state, replay.replayed) == ("B4", "退避", True)
    assert rights_now.calls == []
    assert _counts(db, UUID(event.d5)) == (1, 0, 1, 0)
