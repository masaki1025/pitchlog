"""公開入口の ACK、非開示、R-16、各 T 境界を使い捨て DB で確かめる。"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from test_authz_tenant_context import make_tenant_context
from test_sync_apply_port_change import (
    ChangeProjection,
    ChangeRights,
    ChangeValidator,
)
from test_sync_apply_port_prefix import (
    DenyPrefixRights,
    PrefixProjection,
    PrefixRights,
    PrefixValidator,
    RejectPrefixValidator,
)

from pitchlog.db.sync_protocol.models import OperationEvent
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.repositories.transaction import (
    _TenantTransaction,
    tenant_transaction_scope,
)
from pitchlog.sync import apply as sync_apply
from pitchlog.sync import ordering, ports
from pitchlog.sync.apply import apply_sync_events, apply_sync_request
from pitchlog.sync.crash_points import CrashPoint
from pitchlog.sync.crash_points import testing_crash_hook as _testing_crash_hook
from pitchlog.sync.idempotency import operation_fingerprint
from pitchlog.sync.model import AckResult, SyncEvent, SyncEventBatch, SyncRequest
from pitchlog.sync.prefix_path import P1Result, P1Target, PlayerRegistration
from pitchlog.sync.tokens import (
    IdempotencyLedgerInsertToken,
    OperationEventOrderReadToken,
    OperationEventOrderUpdateToken,
    RejectedOriginalReadToken,
)

from .test_sync_apply_change_boundary import _request as _change_request
from .test_sync_apply_operations_boundary import _SyncDatabase, sync_database
from .test_sync_apply_prefix_path_boundary import _event, prefix_database

__all__ = ("sync_database", "prefix_database")

pytestmark = pytest.mark.requires_db


@pytest.fixture(autouse=True)
def _register_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    """テスト中の合成ポートだけを登録し、製品の登録表を空のままにする。"""
    monkeypatch.setattr(
        ports,
        "PORT_IMPLEMENTATIONS",
        frozenset(
            (cls.__module__, cls.__name__)
            for cls in (
                PrefixRights,
                DenyPrefixRights,
                PrefixProjection,
                PrefixValidator,
                RejectPrefixValidator,
                ChangeRights,
                ChangeProjection,
                ChangeValidator,
            )
        ),
    )


def _invoke(
    db: _SyncDatabase,
    request: SyncRequest,
    *,
    tenant: UUID | None = None,
    rights: PrefixRights | ChangeRights | None = None,
    registration: PlayerRegistration | None = None,
    reject: bool = False,
) -> AckResult | object:
    """実際の公開入口にテスト DB のテナント文脈を渡す。"""
    is_change = request.path == "P3"
    selected_rights = rights or (ChangeRights() if is_change else PrefixRights())
    projection = ChangeProjection() if is_change else PrefixProjection()
    validator = (
        ChangeValidator()
        if is_change
        else RejectPrefixValidator()
        if reject
        else PrefixValidator()
    )
    return apply_sync_request(
        make_tenant_context(tenant or db.tenant_a),
        request,
        selected_rights,
        projection,
        validator,
        registrations={request.events[0].d1: registration}
        if registration and request.events[0].d1 is not None
        else None,
    )


def _count(db: _SyncDatabase, table: str, d5: str) -> int:
    """許可済み同期表の対象 D5 の確定行数を独立に観測する。"""
    if table not in {
        "idempotency_ledger",
        "operation_events",
        "rejected_event_originals",
        "evacuated_event_originals",
    }:
        raise ValueError("試験が許す表でない")
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            f"SELECT count(*) FROM {table} WHERE tenant_id = %s AND d5 = %s",
            (db.tenant_a, UUID(d5)),
        )
        row = cursor.fetchone()
    db.catalog.applicator.rollback()
    assert row is not None
    return row[0]


def _invoke_events(
    db: _SyncDatabase,
    batch: SyncEventBatch,
    *,
    registrations: dict[int, PlayerRegistration] | None = None,
    rights: PrefixRights | DenyPrefixRights | None = None,
) -> AckResult:
    """混在バッチを製品の公開入口へ渡す。"""
    result = apply_sync_events(
        make_tenant_context(db.tenant_a),
        batch,
        rights or PrefixRights(),
        PrefixProjection(),
        PrefixValidator(),
        registrations=registrations,
    )
    assert isinstance(result, AckResult)
    return result


def test_mixed_event_batch_single_ack_routes_and_replays(
    prefix_database: _SyncDatabase,
) -> None:
    """P2・P1・P2 を一要求で確定し、再送は同じ指紋で全件再掲する。"""
    db = prefix_database
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT home_team_record_id FROM games WHERE tenant_id = %s AND id = %s",
            (db.tenant_a, db.game_a),
        )
        team = cursor.fetchone()
    db.catalog.applicator.rollback()
    assert team is not None
    temporary = uuid4()
    registration = PlayerRegistration(temporary, team[0], "混在登録", "active")
    first = _event(db.game_a, d1=1, d4="1", kind="play_input")
    second = _event(
        db.game_a,
        d1=2,
        d4="1",
        kind="player_registration",
        payload={"player_id": str(temporary)},
    )
    third = _event(db.game_a, d1=3, d4="1", kind="game_end_declaration")
    batch = SyncEventBatch(str(db.game_a), "1", (third, second, first), v12="proof")
    result = _invoke_events(db, batch, registrations={2: registration})
    assert (result.boundary, result.d3) == ("B1", 3)
    assert [(row.d1, row.state) for row in result.a5] == [
        (1, "受理"),
        (2, "受理"),
        (3, "受理"),
    ]
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT d5, source_fingerprint FROM idempotency_ledger "
            "WHERE tenant_id = %s AND d5 IN (%s, %s, %s)",
            (db.tenant_a, UUID(first.d5), UUID(second.d5), UUID(third.d5)),
        )
        saved = dict(cursor.fetchall())
    db.catalog.applicator.rollback()
    assert saved == {
        UUID(first.d5): operation_fingerprint(first, "P2", None),
        UUID(second.d5): operation_fingerprint(second, "P1", registration),
        UUID(third.d5): operation_fingerprint(third, "P2", None),
    }
    replay = _invoke_events(db, batch, registrations={2: registration})
    assert (replay.boundary, replay.d3) == ("B1", 3)
    assert [row.state for row in replay.a5] == ["重複"] * 3
    assert all(_count(db, "operation_events", event.d5) == 1 for event in batch.events)


def test_mixed_event_batch_stops_after_content_rejection(
    prefix_database: _SyncDatabase,
) -> None:
    """P2 の拒否までを確定し、後続 P1 を同じ ACK で未処理にする。"""
    db = prefix_database
    first = _event(db.game_a, d1=1, d4="1", kind="play_input")
    rejected = _event(
        db.game_a,
        d1=2,
        d4="1",
        kind="game_end_declaration",
        payload={"player_id": 1},
    )
    later = _event(db.game_a, d1=3, d4="1", kind="undo")
    batch = SyncEventBatch(str(db.game_a), "1", (later, rejected, first), v12="proof")
    result = _invoke_events(db, batch)
    assert (result.boundary, result.b3_branch, result.d3) == ("B3", "B3a", 1)
    assert [(row.d1, row.state) for row in result.a5] == [
        (1, "受理"),
        (2, "拒否"),
        (3, "未処理"),
    ]
    assert _count(db, "operation_events", first.d5) == 1
    assert _count(db, "rejected_event_originals", rejected.d5) == 1
    assert _count(db, "idempotency_ledger", later.d5) == 0
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT payload->>'path' FROM rejected_event_originals "
            "WHERE tenant_id = %s AND d5 = %s",
            (db.tenant_a, UUID(rejected.d5)),
        )
        stored_path = cursor.fetchone()
    db.catalog.applicator.rollback()
    assert stored_path == ("P2",)


def test_mixed_event_batch_revision_inherits_rejected_p2_route(
    prefix_database: _SyncDatabase,
) -> None:
    """改訂版は T9 に保存した P2 を継ぎ、同じ D2 の位置で適用される。"""
    db = prefix_database
    original = _event(
        db.game_a, d1=1, d4="1", kind="play_input", payload={"player_id": 1}
    )
    rejected = _invoke_events(
        db, SyncEventBatch(str(db.game_a), "1", (original,), v12="proof")
    )
    assert (rejected.boundary, rejected.a5[0].state) == ("B3", "拒否")
    revision = _event(
        db.game_a,
        d1=1,
        d4="1",
        kind="play_input",
        revision=True,
        rejected_d5=UUID(original.d5),
    )
    batch = SyncEventBatch(str(db.game_a), "1", (revision,), v12="proof")
    result = _invoke_events(db, batch)
    assert (result.boundary, result.d3, result.a5[0].state) == ("B1", 1, "受理")
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT source_fingerprint FROM idempotency_ledger "
            "WHERE tenant_id = %s AND d5 = %s",
            (db.tenant_a, UUID(revision.d5)),
        )
        fingerprint = cursor.fetchone()
    db.catalog.applicator.rollback()
    assert fingerprint == (operation_fingerprint(revision, "P2", None),)
    replay = _invoke_events(db, batch)
    assert replay.a5[0].state == "重複"


@pytest.mark.parametrize("deny_right", [False, True])
def test_missing_revision_original_keeps_rights_and_saves_own_route(
    prefix_database: _SyncDatabase, deny_right: bool
) -> None:
    """原本不在の改訂版も ⑤ を通り、B3a は T9 を保存し、B4 は退避する。

    経路は自身の V5 で決め、後から原本ができても保存済みの指紋で再掲する。
    """
    db = prefix_database
    original_d5 = uuid4()
    revision = _event(
        db.game_a,
        d1=1,
        d4="1",
        kind="play_input",
        revision=True,
        rejected_d5=original_d5,
    )
    batch = SyncEventBatch(str(db.game_a), "1", (revision,), v12="proof")
    rights = DenyPrefixRights() if deny_right else None
    missing = _invoke_events(db, batch, rights=rights)
    if deny_right:
        assert (missing.boundary, missing.a5[0].state) == ("B4", "退避")
        assert _count(db, "evacuated_event_originals", revision.d5) == 1
        assert _count(db, "rejected_event_originals", revision.d5) == 0
    else:
        assert (missing.boundary, missing.b3_branch, missing.a5[0].state) == (
            "B3",
            "B3a",
            "拒否",
        )
        assert _count(db, "rejected_event_originals", revision.d5) == 1
        assert _count(db, "evacuated_event_originals", revision.d5) == 0
    assert _count(db, "idempotency_ledger", revision.d5) == 1
    assert _count(db, "operation_events", revision.d5) == 0

    original = _event(db.game_a, d1=1, d4="1", kind="undo", d5=original_d5)
    seeded = _invoke(
        db,
        SyncRequest("P1", str(db.game_a), (original,), d4="1", v12="proof"),
        reject=True,
    )
    assert isinstance(seeded, AckResult)
    assert _count(db, "rejected_event_originals", original.d5) == 1

    resumed = _invoke_events(db, batch, rights=rights)
    assert resumed.a5[0].state == missing.a5[0].state
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT source_fingerprint FROM idempotency_ledger "
            "WHERE tenant_id = %s AND d5 = %s",
            (db.tenant_a, UUID(revision.d5)),
        )
        saved = cursor.fetchall()
    db.catalog.applicator.rollback()
    assert saved == [(operation_fingerprint(revision, "P2", None),)]
    assert _count(db, "operation_events", revision.d5) == 0


def test_saved_revision_replays_when_original_is_temporarily_unseen(
    prefix_database: _SyncDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """保存済み D5 は原本の可視性が変わっても元の経路で再掲する。"""
    db = prefix_database
    original = _event(db.game_a, d1=1, d4="1", kind="play_input")
    seeded = _invoke(
        db,
        SyncRequest("P1", str(db.game_a), (original,), d4="1", v12="proof"),
        reject=True,
    )
    assert isinstance(seeded, AckResult)
    assert seeded.boundary == "B3"
    revision = _event(
        db.game_a,
        d1=1,
        d4="1",
        kind="play_input",
        revision=True,
        rejected_d5=UUID(original.d5),
    )
    batch = SyncEventBatch(str(db.game_a), "1", (revision,), v12="proof")
    first = _invoke_events(db, batch)
    assert (first.boundary, first.a5[0].state) == ("B1", "受理")
    original_run = _TenantTransaction.run

    def hide_original(
        self: _TenantTransaction, token: TenantOperationToken
    ) -> TenantOperationResult:
        if isinstance(token, RejectedOriginalReadToken) and token.d5 == UUID(
            original.d5
        ):
            return TenantOperationResult(())
        return original_run(self, token)

    monkeypatch.setattr(_TenantTransaction, "run", hide_original)
    replay = _invoke_events(db, batch)
    assert (replay.boundary, replay.a5[0].state) == ("B1", "重複")
    assert _count(db, "operation_events", revision.d5) == 1


def test_mixed_event_batch_escrow_keeps_each_event_fingerprint(
    prefix_database: _SyncDatabase,
) -> None:
    """⑤不成立の P2/P1 を各経路の指紋で退避し、同じ内容を再掲する。"""
    db = prefix_database
    first = _event(db.game_a, d1=1, d4="1", kind="play_input")
    second = _event(db.game_a, d1=2, d4="1", kind="undo")
    batch = SyncEventBatch(str(db.game_a), "1", (second, first), v12="old-proof")
    result = _invoke_events(db, batch, rights=DenyPrefixRights())
    assert result.boundary == "B4"
    assert [(row.d1, row.state) for row in result.a5] == [(1, "退避"), (2, "退避")]
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT d5, source_fingerprint FROM idempotency_ledger "
            "WHERE tenant_id = %s AND d5 IN (%s, %s)",
            (db.tenant_a, UUID(first.d5), UUID(second.d5)),
        )
        saved = dict(cursor.fetchall())
    db.catalog.applicator.rollback()
    assert saved == {
        UUID(first.d5): operation_fingerprint(first, "P2", None),
        UUID(second.d5): operation_fingerprint(second, "P1", None),
    }
    replay = _invoke_events(db, batch, rights=DenyPrefixRights())
    assert [row.state for row in replay.a5] == ["退避", "退避"]
    assert all(
        _count(db, "evacuated_event_originals", event.d5) == 1 for event in batch.events
    )


def test_mixed_event_batch_gap_is_one_b2_boundary(
    prefix_database: _SyncDatabase,
) -> None:
    """混在バッチの D1 欠落を一つの B2 で止める。"""
    db = prefix_database
    first = _event(db.game_a, d1=1, d4="1", kind="play_input")
    third = _event(db.game_a, d1=3, d4="1", kind="game_end_declaration")
    result = _invoke_events(
        db, SyncEventBatch(str(db.game_a), "1", (third, first), v12="proof")
    )
    assert (result.boundary, result.d3) == ("B2", 1)
    assert [(row.d1, row.state) for row in result.a5] == [(1, "受理"), (3, "未処理")]
    assert _count(db, "idempotency_ledger", third.d5) == 0


def _game_state(db: _SyncDatabase) -> tuple[int, int]:
    """現在の D3 とテナントの同期意図行数を独立 SQL で読む。

    ①試合以外の範囲(②〜⑤)の行は選択子で game_id を持たないため、
    試合で絞らずテナントの同期意図(接頭辞 sync:)を数える。
    """
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT confirmed_watermark FROM recording_generations "
            "WHERE tenant_id = %s AND game_id = %s AND generation = 1",
            (db.tenant_a, db.game_a),
        )
        watermark = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) FROM invalidation_intents "
            "WHERE tenant_id = %s AND intent_id LIKE 'sync:%%'",
            (db.tenant_a,),
        )
        intent_count = cursor.fetchone()
    db.catalog.applicator.rollback()
    assert watermark is not None and intent_count is not None
    return watermark[0], intent_count[0]


def _set_in_progress(db: _SyncDatabase) -> None:
    """P3 の対象試合を進行中にする。"""
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "UPDATE games SET status = 'in_progress' WHERE tenant_id = %s AND id = %s",
            (db.tenant_a, db.game_a),
        )
    db.catalog.applicator.commit()


def test_gap_example_preclassified_b3b_is_unprocessed(
    prefix_database: _SyncDatabase,
) -> None:
    """SP 6-3: D3=4、5 欠落、6 未使用、7 異内容で B2 と A5 未処理。"""
    db = prefix_database
    first_events = tuple(_event(db.game_a, d1=d1, d4="1") for d1 in range(1, 5))
    first = SyncRequest("P1", str(db.game_a), first_events, d4="1", v12="proof")
    accepted = _invoke(db, first)
    assert isinstance(accepted, AckResult)
    assert (accepted.boundary, accepted.d3) == ("B1", 4)

    later = _event(db.game_a, d1=7, d4="1")
    with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
        scope.run(
            IdempotencyLedgerInsertToken(
                UUID(later.d5),
                "accepted",
                "a" * 64,
                '{"state":"受理","d3":7,"temporary_id_mapping":{}}',
            )
        )
    # 欠番なら ⑦の V5 不成立より B2 を先に決める。
    gap = SyncEvent(str(uuid4()), str(db.game_a), 6, "1", v5="unknown", v7={})
    mixed = SyncRequest("P1", str(db.game_a), (later, gap), d4="1", v12="proof")
    result = _invoke(db, mixed)
    assert isinstance(result, AckResult)
    assert (result.boundary, result.d3, result.b3_branch) == ("B2", 4, None)
    assert [(item.d1, item.state) for item in result.a5] == [
        (6, "未処理"),
        (7, "未処理"),
    ]
    assert _count(db, "idempotency_ledger", gap.d5) == 0
    assert _count(db, "operation_events", gap.d5) == 0
    assert _count(db, "idempotency_ledger", later.d5) == 1


def test_gap_before_only_existing_conflict_is_b2_not_b3b(
    prefix_database: _SyncDatabase,
) -> None:
    """D3=4 で既存異内容の 7 だけを送ると、5 の欠落で B2・7 は未処理。"""
    db = prefix_database
    first_events = tuple(_event(db.game_a, d1=d1, d4="1") for d1 in range(1, 5))
    accepted = _invoke(
        db, SyncRequest("P1", str(db.game_a), first_events, d4="1", v12="proof")
    )
    assert isinstance(accepted, AckResult) and accepted.d3 == 4
    later = _event(db.game_a, d1=7, d4="1")
    with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
        scope.run(
            IdempotencyLedgerInsertToken(
                UUID(later.d5),
                "accepted",
                "a" * 64,
                '{"state":"受理","d3":7,"temporary_id_mapping":{}}',
            )
        )
    result = _invoke(
        db, SyncRequest("P1", str(db.game_a), (later,), d4="1", v12="proof")
    )
    assert isinstance(result, AckResult)
    assert (result.boundary, result.d3, result.b3_branch) == ("B2", 4, None)
    assert [(item.d1, item.state) for item in result.a5] == [(7, "未処理")]
    assert _count(db, "idempotency_ledger", later.d5) == 1


def test_b4_request_replays_existing_and_escrows_every_unused(
    prefix_database: _SyncDatabase,
) -> None:
    """⑤ 不成立の要求: 受理済みは再掲(重複)、未使用は全件退避し、B4 で止めない。"""
    db = prefix_database
    first_events = tuple(_event(db.game_a, d1=d1, d4="1") for d1 in range(1, 4))
    accepted = _invoke(
        db, SyncRequest("P1", str(db.game_a), first_events, d4="1", v12="proof")
    )
    assert isinstance(accepted, AckResult) and accepted.d3 == 3
    unused = tuple(_event(db.game_a, d1=d1, d4="1") for d1 in (4, 5))
    resend = SyncRequest(
        "P1", str(db.game_a), (*first_events, *unused), d4="1", v12="old-proof"
    )
    result = _invoke(db, resend, rights=DenyPrefixRights())
    assert isinstance(result, AckResult)
    assert result.boundary == "B4"
    assert [(item.d1, item.state) for item in result.a5] == [
        (1, "重複"),
        (2, "重複"),
        (3, "重複"),
        (4, "退避"),
        (5, "退避"),
    ]
    for event in unused:
        assert _count(db, "evacuated_event_originals", event.d5) == 1
        assert _count(db, "operation_events", event.d5) == 0
    for event in first_events:
        assert _count(db, "evacuated_event_originals", event.d5) == 0
    assert _game_state(db)[0] == 3


@pytest.mark.parametrize("reverse", [False, True])
def test_b4_duplicate_d5_replays_only_saved_d1_and_escrows_unused(
    prefix_database: _SyncDatabase, reverse: bool
) -> None:
    """⑤不成立でも同じ D5 の保存済み結果と別 D1 の異内容を分けて扱う。"""
    db = prefix_database
    saved = _event(db.game_a, d1=1, d4="1")
    accepted = _invoke(
        db, SyncRequest("P1", str(db.game_a), (saved,), d4="1", v12="proof")
    )
    assert isinstance(accepted, AckResult)
    assert [(row.d1, row.state) for row in accepted.a5] == [(1, "受理")]
    _hand_over_generation(db)
    conflict = _event(db.game_a, d1=2, d4="1", d5=UUID(saved.d5))
    unused = _event(db.game_a, d1=3, d4="1")
    events = (conflict, saved, unused) if reverse else (saved, conflict, unused)
    request = SyncRequest("P1", str(db.game_a), events, d4="1", v12="old-proof")

    first = _invoke(db, request, rights=DenyPrefixRights())
    assert isinstance(first, AckResult)
    assert (first.boundary, first.d3, first.b3_branch) == ("B4", 1, None)
    assert [(row.d1, row.state, row.reason) for row in first.a5] == [
        (1, "重複", None),
        (2, "未処理", None),
        (3, "退避", None),
    ]

    # 退避後は全 D5 が使用済み。再送時は⑤を通らず、⑥で B3b を確定する。
    resent = _invoke(db, request, rights=DenyPrefixRights())
    assert isinstance(resent, AckResult)
    assert (resent.boundary, resent.d3, resent.b3_branch) == ("B3", 1, "B3b")
    assert [(row.d1, row.state) for row in resent.a5] == [
        (1, "重複"),
        (2, "拒否"),
        (3, "未処理"),
    ]
    assert _count(db, "idempotency_ledger", saved.d5) == 1
    assert _count(db, "operation_events", saved.d5) == 1
    assert _count(db, "rejected_event_originals", saved.d5) == 0
    assert _count(db, "evacuated_event_originals", saved.d5) == 0
    assert _count(db, "idempotency_ledger", unused.d5) == 1
    assert _count(db, "evacuated_event_originals", unused.d5) == 1
    assert _count(db, "rejected_event_originals", unused.d5) == 0


def test_duplicate_d5_uses_each_d1_registration_in_real_db(
    prefix_database: _SyncDatabase,
) -> None:
    """同じ D5 の再送で登録値を取り違えると保存済み結果を再掲できない。"""
    db = prefix_database
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT home_team_record_id FROM games WHERE tenant_id = %s AND id = %s",
            (db.tenant_a, db.game_a),
        )
        row = cursor.fetchone()
    db.catalog.applicator.rollback()
    assert row is not None
    temporary1, temporary2 = uuid4(), uuid4()
    registration1 = PlayerRegistration(temporary1, row[0], "登録一", "active")
    registration2 = PlayerRegistration(temporary2, row[0], "登録二", "active")
    saved = _event(
        db.game_a,
        d1=1,
        d4="1",
        kind="player_registration",
        payload={"player_id": str(temporary1)},
    )
    first = _invoke(
        db,
        SyncRequest("P1", str(db.game_a), (saved,), d4="1", v12="proof"),
        registration=registration1,
    )
    assert isinstance(first, AckResult) and first.a5[0].state == "受理"
    conflict = _event(
        db.game_a,
        d1=2,
        d4="1",
        d5=UUID(saved.d5),
        kind="player_registration",
        payload={"player_id": str(temporary2)},
    )
    request = SyncRequest("P1", str(db.game_a), (conflict, saved), d4="1", v12="proof")
    result = apply_sync_request(
        make_tenant_context(db.tenant_a),
        request,
        PrefixRights(),
        PrefixProjection(),
        PrefixValidator(),
        registrations={1: registration1, 2: registration2},
    )
    assert isinstance(result, AckResult)
    assert (result.boundary, result.b3_branch, result.d3) == ("B3", "B3b", 1)
    assert [(item.d1, item.state) for item in result.a5] == [(1, "重複"), (2, "拒否")]
    assert _count(db, "idempotency_ledger", saved.d5) == 1
    assert _count(db, "operation_events", saved.d5) == 1
    assert _count(db, "rejected_event_originals", saved.d5) == 0


def test_duplicate_d5_uses_each_d1_target_in_real_db(
    prefix_database: _SyncDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同じ D5 の 2 件を実 DB に通し、各 D1 の解決済み対象を観測する。"""
    db = prefix_database
    source = _event(db.game_a, d1=1, d4="1")
    seeded = _invoke(
        db, SyncRequest("P1", str(db.game_a), (source,), d4="1", v12="proof")
    )
    assert isinstance(seeded, AckResult) and seeded.a5[0].state == "受理"
    saved = SyncEvent(
        str(uuid4()),
        str(db.game_a),
        2,
        "1",
        v5="undo",
        v7={},
        v10={"game": str(db.game_a), "d4": "1", "d1": 1},
    )
    target1 = P1Target(db.game_a, 1, 1)
    accepted = apply_sync_request(
        make_tenant_context(db.tenant_a),
        SyncRequest("P1", str(db.game_a), (saved,), d4="1", v12="proof"),
        PrefixRights(),
        PrefixProjection(),
        PrefixValidator(),
        targets={2: target1},
    )
    assert isinstance(accepted, AckResult) and accepted.a5[0].state == "受理"
    conflict = SyncEvent(
        saved.d5,
        str(db.game_a),
        3,
        "1",
        v5="undo",
        v7={},
        v10={"game": str(db.game_a), "d4": "1", "d1": 2},
    )
    target2 = P1Target(db.game_a, 1, 2)
    seen: list[tuple[int | None, P1Target | None]] = []
    original = sync_apply.apply_p1_event

    def observe(*args: Any, **kwargs: Any) -> P1Result:
        event: SyncEvent = args[1]
        seen.append((event.d1, kwargs.get("target")))
        return original(*args, **kwargs)

    monkeypatch.setattr(sync_apply, "apply_p1_event", observe)
    request = SyncRequest("P1", str(db.game_a), (conflict, saved), d4="1", v12="proof")
    result = apply_sync_request(
        make_tenant_context(db.tenant_a),
        request,
        PrefixRights(),
        PrefixProjection(),
        PrefixValidator(),
        targets={2: target1, 3: target2},
    )
    assert isinstance(result, AckResult)
    assert (result.boundary, result.b3_branch, result.d3) == ("B3", "B3b", 2)
    assert [(item.d1, item.state) for item in result.a5] == [(2, "重複"), (3, "拒否")]
    assert seen == [(2, target1), (3, target2)]
    assert _count(db, "idempotency_ledger", saved.d5) == 1


def test_valid_request_resending_escrowed_d5_does_not_report_b4(
    prefix_database: _SyncDatabase,
) -> None:
    """V12 が一致する要求で退避済み D5 を再送しても、境界を B4 にしない(U-14)。"""
    db = prefix_database
    escrowed = _event(db.game_a, d1=1, d4="1")
    first = _invoke(
        db,
        SyncRequest("P1", str(db.game_a), (escrowed,), d4="1", v12="old-proof"),
        rights=DenyPrefixRights(),
    )
    assert isinstance(first, AckResult)
    assert (first.boundary, first.a5[0].state) == ("B4", "退避")
    resend = _invoke(
        db, SyncRequest("P1", str(db.game_a), (escrowed,), d4="1", v12="proof")
    )
    assert isinstance(resend, AckResult)
    assert (resend.boundary, resend.d3) == ("B1", 0)
    assert [(item.d1, item.state) for item in resend.a5] == [(1, "退避")]
    assert _count(db, "evacuated_event_originals", escrowed.d5) == 1


def _hand_over_generation(db: _SyncDatabase) -> None:
    """記録権の引き継ぎを模す: 世代 1 を失効・退役させ、D3 = 0 の世代 2 を作る。"""
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "UPDATE recording_generations SET revoked_at = now(), retired_at = now() "
            "WHERE tenant_id = %s AND game_id = %s AND generation = 1",
            (db.tenant_a, db.game_a),
        )
        cursor.execute(
            "INSERT INTO recording_generations (tenant_id, game_id, generation, "
            "kind, issuance_order, holder_device) "
            "VALUES (%s, %s, 2, 'normal', 2, 'new-device')",
            (db.tenant_a, db.game_a),
        )
    db.catalog.applicator.commit()


def test_old_generation_resend_replays_without_current_gap(
    prefix_database: _SyncDatabase,
) -> None:
    """引き継ぎ後に旧 D4 の受理済みを再送すると、現世代の D3 で B2 にせず再掲する。"""
    db = prefix_database
    events = tuple(_event(db.game_a, d1=d1, d4="1") for d1 in range(1, 4))
    accepted = _invoke(
        db, SyncRequest("P1", str(db.game_a), events, d4="1", v12="proof")
    )
    assert isinstance(accepted, AckResult) and accepted.d3 == 3
    _hand_over_generation(db)
    resend = _invoke(
        db, SyncRequest("P1", str(db.game_a), events[2:], d4="1", v12="proof")
    )
    assert isinstance(resend, AckResult)
    assert resend.boundary != "B2"
    assert [(item.d1, item.state) for item in resend.a5] == [(3, "重複")]
    # ACK の D3 は要求の D4(世代 1)の D3 で、現世代(D3 = 0)を起点に後退しない。
    assert resend.d3 == 3


def test_old_generation_saved_escrow_after_gap_is_unprocessed(
    prefix_database: _SyncDatabase,
) -> None:
    """旧 D4 の退避済み D5 も要求世代の D3 から欠番を判定する。"""
    db = prefix_database
    accepted_events = tuple(_event(db.game_a, d1=d1, d4="1") for d1 in range(1, 4))
    accepted = _invoke(
        db, SyncRequest("P1", str(db.game_a), accepted_events, d4="1", v12="proof")
    )
    assert isinstance(accepted, AckResult) and accepted.d3 == 3
    later = _event(db.game_a, d1=7, d4="1")
    escrow = _invoke(
        db,
        SyncRequest("P4", str(db.game_a), (later,), d4="1", v12="old-proof"),
        rights=DenyPrefixRights(),
    )
    assert isinstance(escrow, AckResult)
    assert (escrow.boundary, escrow.a5[0].state) == ("B4", "退避")
    assert _count(db, "evacuated_event_originals", later.d5) == 1
    _hand_over_generation(db)

    resend = _invoke(
        db,
        SyncRequest("P4", str(db.game_a), (later,), d4="1", v12="old-proof"),
        rights=DenyPrefixRights(),
    )
    assert isinstance(resend, AckResult)
    assert (resend.boundary, resend.d3, resend.a5[0].state) == (
        "B2",
        3,
        "未処理",
    )
    assert _count(db, "evacuated_event_originals", later.d5) == 1


def test_p4_resend_replays_escrow_with_p4_fingerprint(
    prefix_database: _SyncDatabase,
) -> None:
    """P4 の再送は P4 の指紋で照合し、保存済みの退避を異内容(B3b)にしない。"""
    db = prefix_database
    first = _event(db.game_a, d1=1, d4="1")
    escrow = _invoke(
        db,
        SyncRequest("P4", str(db.game_a), (first,), d4="1", v12="old-proof"),
        rights=DenyPrefixRights(),
    )
    assert isinstance(escrow, AckResult)
    assert (escrow.boundary, escrow.a5[0].state) == ("B4", "退避")
    second = _event(db.game_a, d1=2, d4="1")
    resend = _invoke(
        db,
        SyncRequest("P4", str(db.game_a), (first, second), d4="1", v12="old-proof"),
        rights=DenyPrefixRights(),
    )
    assert isinstance(resend, AckResult)
    assert resend.boundary == "B4"
    assert [(item.d1, item.state, item.reason) for item in resend.a5] == [
        (1, "退避", None),
        (2, "退避", None),
    ]
    for event in (first, second):
        assert _count(db, "evacuated_event_originals", event.d5) == 1


def test_b4_request_leaves_conflict_unprocessed_without_t9(
    prefix_database: _SyncDatabase,
) -> None:
    """⑤の B4 は保存済み結果だけ再掲し、異内容候補を未処理のまま残す。"""
    db = prefix_database
    escrowed = _event(db.game_a, d1=1, d4="1")
    first = _invoke(
        db,
        SyncRequest("P1", str(db.game_a), (escrowed,), d4="1", v12="old-proof"),
        rights=DenyPrefixRights(),
    )
    assert isinstance(first, AckResult) and first.boundary == "B4"
    conflict = _event(db.game_a, d1=2, d4="1")
    with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
        scope.run(
            IdempotencyLedgerInsertToken(
                UUID(conflict.d5),
                "accepted",
                "b" * 64,
                '{"state":"受理","d3":2,"temporary_id_mapping":{}}',
            )
        )
    _hand_over_generation(db)
    unused = _event(db.game_a, d1=3, d4="1")
    result = _invoke(
        db,
        SyncRequest(
            "P1", str(db.game_a), (escrowed, conflict, unused), d4="1", v12="x"
        ),
        rights=DenyPrefixRights(),
    )
    assert isinstance(result, AckResult)
    assert (result.boundary, result.b3_branch) == ("B4", None)
    assert [(item.d1, item.state) for item in result.a5] == [
        (1, "退避"),
        (2, "未処理"),
        (3, "退避"),
    ]
    assert result.a5[1].reason is None
    assert _count(db, "idempotency_ledger", conflict.d5) == 1
    assert _count(db, "rejected_event_originals", conflict.d5) == 0
    assert _count(db, "evacuated_event_originals", unused.d5) == 1


def test_contiguous_invalid_content_commits_b3a_original(
    prefix_database: _SyncDatabase,
) -> None:
    """⑦の不正 V5 は実入口から P5/T9 へ進み、拒否理由を ACK に載せる。"""
    db = prefix_database
    event = SyncEvent(str(uuid4()), str(db.game_a), 1, "1", v5="unknown", v7={})
    request = SyncRequest("P1", str(db.game_a), (event,), d4="1", v12="proof")
    result = _invoke(db, request)
    assert isinstance(result, AckResult)
    assert (result.boundary, result.b3_branch, result.d3) == ("B3", "B3a", 0)
    assert result.a5[0].state == "拒否"
    assert result.reason is not None and "V5" in result.reason
    assert _count(db, "idempotency_ledger", event.d5) == 1
    assert _count(db, "rejected_event_originals", event.d5) == 1
    assert _count(db, "operation_events", event.d5) == 0


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("reference_type", "選手参照は UUID 文字列が必要"),
        ("reference_parse", "選手参照は UUID 文字列が必要"),
        ("reference_canonical", "選手参照は正規 UUID が必要"),
        ("reference_field", "V5 で定義されない選手参照位置"),
        ("v6_range", "P2 の V6 は非負の bigint が必要"),
    ],
)
def test_d5_content_rejection_commits_t9_and_replays_b3a(
    prefix_database: _SyncDatabase, case: str, reason: str
) -> None:
    """D-5 の各内容拒否を原本・台帳・理由と一体で保存し再掲する。"""
    db = prefix_database
    if case == "v6_range":
        event = SyncEvent(
            str(uuid4()),
            str(db.game_a),
            1,
            "1",
            v5="game_end_declaration",
            v6=2**63,
            v7={},
        )
        path = "P2"
    else:
        payload: dict[str, object]
        if case == "reference_type":
            payload = {"player_id": 1}
        elif case == "reference_parse":
            payload = {"player_id": "invalid-uuid"}
        elif case == "reference_canonical":
            payload = {"player_id": str(uuid4()).upper()}
        else:
            payload = {"batter_id": str(uuid4())}
        event = _event(db.game_a, d4="1", payload=payload)
        path = "P1"
    request = SyncRequest(path, str(db.game_a), (event,), d4="1", v12="proof")
    result = _invoke(db, request)
    assert isinstance(result, AckResult)
    assert (result.boundary, result.b3_branch, result.d3) == ("B3", "B3a", 0)
    assert (result.a5[0].state, result.reason) == ("拒否", reason)
    assert _count(db, "idempotency_ledger", event.d5) == 1
    assert _count(db, "rejected_event_originals", event.d5) == 1
    assert _count(db, "operation_events", event.d5) == 0
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT kind, result, reason FROM idempotency_ledger "
            "WHERE tenant_id = %s AND d5 = %s",
            (db.tenant_a, UUID(event.d5)),
        )
        assert cursor.fetchone() == ("rejected", {"state": "拒否", "d3": 0}, reason)
        cursor.execute(
            "SELECT payload FROM rejected_event_originals "
            "WHERE tenant_id = %s AND d5 = %s",
            (db.tenant_a, UUID(event.d5)),
        )
        original = cursor.fetchone()
        assert original is not None
        assert original[0]["d5"] == event.d5
        cursor.execute(
            "SELECT confirmed_watermark FROM recording_generations "
            "WHERE tenant_id = %s AND game_id = %s AND generation = 1",
            (db.tenant_a, db.game_a),
        )
        assert cursor.fetchone() == (0,)
    db.catalog.applicator.rollback()

    replay = _invoke(db, request)
    assert isinstance(replay, AckResult)
    assert (replay.boundary, replay.b3_branch, replay.d3) == ("B3", "B3a", 0)
    assert replay.a5[0].state == "拒否"
    assert _count(db, "idempotency_ledger", event.d5) == 1
    assert _count(db, "rejected_event_originals", event.d5) == 1

    if case != "v6_range":
        revised = _event(
            db.game_a,
            d4="1",
            revision=True,
            rejected_d5=UUID(event.d5),
        )
        resumed = _invoke(
            db,
            SyncRequest("P1", str(db.game_a), (revised,), d4="1", v12="proof"),
        )
        assert isinstance(resumed, AckResult)
        assert (resumed.boundary, resumed.d3, resumed.a5[0].state) == (
            "B1",
            1,
            "受理",
        )


def test_d5_content_rejection_rolls_back_t5_renumbering(
    prefix_database: _SyncDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P2 の再採番後に内容拒否しても T5 だけを残さず T9 を確定する。"""
    db = prefix_database
    for d1, d2 in ((1, 9), (2, 10), (3, 11)):
        accepted = SyncEvent(
            str(uuid4()),
            str(db.game_a),
            d1,
            "1",
            v5="play_input",
            v6=d2,
            v7={},
            v8={},
        )
        result = _invoke(
            db,
            SyncRequest("P2", str(db.game_a), (accepted,), d4="1", v12="proof"),
        )
        assert isinstance(result, AckResult) and result.a5[0].state == "受理"

    updates: list[OperationEventOrderUpdateToken] = []
    positions_after_assign: list[tuple[tuple[object, object], ...]] = []
    event_columns = tuple(OperationEvent.__table__.c.keys())
    d1_column = event_columns.index("d1")
    d2_column = event_columns.index("d2")
    original_assign = ordering._assign_d2

    def observe_assign(
        scope: _TenantTransaction, game_id: UUID, desired: int
    ) -> int | None:
        """T5 の UPDATE token が実際に実行されたことを観測する。"""

        class ObservedScope:
            """採番器の操作を本物の取引へ渡して UPDATE だけ数える。"""

            def run(self, token: TenantOperationToken) -> TenantOperationResult:
                """成功した再採番 UPDATE を記録する。"""
                result = scope.run(token)
                if isinstance(token, OperationEventOrderUpdateToken):
                    updates.append(token)
                return result

        assigned = original_assign(
            cast(_TenantTransaction, ObservedScope()), game_id, desired
        )
        rows = scope.run(OperationEventOrderReadToken(game_id, -1, 256)).rows
        positions_after_assign.append(
            tuple((row[d1_column], row[d2_column]) for row in rows)
        )
        return assigned

    monkeypatch.setattr(ordering, "_assign_d2", observe_assign)

    rejected = SyncEvent(
        str(uuid4()),
        str(db.game_a),
        4,
        "1",
        v5="play_input",
        v6=10,
        v7={"player_id": 1},
        v8={},
    )
    result = _invoke(
        db,
        SyncRequest("P2", str(db.game_a), (rejected,), d4="1", v12="proof"),
    )
    assert isinstance(result, AckResult)
    assert (result.boundary, result.b3_branch, result.d3) == ("B3", "B3a", 3)
    assert result.a5[0].state == "拒否"
    assert [token.d2 for token in updates] == [12, 11]
    assert positions_after_assign == [((1, 9), (2, 11), (3, 12))]
    assert _count(db, "idempotency_ledger", rejected.d5) == 1
    assert _count(db, "rejected_event_originals", rejected.d5) == 1
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT d1, d2 FROM operation_events WHERE tenant_id = %s "
            "AND game_id = %s ORDER BY d1",
            (db.tenant_a, db.game_a),
        )
        assert cursor.fetchall() == [(1, 9), (2, 10), (3, 11)]
        cursor.execute(
            "SELECT confirmed_watermark FROM recording_generations "
            "WHERE tenant_id = %s AND game_id = %s AND generation = 1",
            (db.tenant_a, db.game_a),
        )
        assert cursor.fetchone() == (3,)
    db.catalog.applicator.rollback()


def test_d5_content_rejection_stops_mixed_batch_after_t9(
    prefix_database: _SyncDatabase,
) -> None:
    """受理・D-5 拒否・後続を一要求で処理し、拒否の次を未処理にする。"""
    db = prefix_database
    accepted = _event(db.game_a, d1=1, d4="1")
    rejected = _event(db.game_a, d1=2, d4="1", payload={"player_id": 1})
    later = _event(db.game_a, d1=3, d4="1")
    request = SyncRequest(
        "P1", str(db.game_a), (later, rejected, accepted), d4="1", v12="proof"
    )
    result = _invoke(db, request)
    assert isinstance(result, AckResult)
    assert (result.boundary, result.b3_branch, result.d3) == ("B3", "B3a", 1)
    assert [(item.d1, item.state) for item in result.a5] == [
        (1, "受理"),
        (2, "拒否"),
        (3, "未処理"),
    ]
    assert result.a5[1].reason == "選手参照は UUID 文字列が必要"
    assert result.a5[2].reason is None
    assert _count(db, "idempotency_ledger", accepted.d5) == 1
    assert _count(db, "idempotency_ledger", rejected.d5) == 1
    assert _count(db, "idempotency_ledger", later.d5) == 0
    assert _count(db, "rejected_event_originals", accepted.d5) == 0
    assert _count(db, "rejected_event_originals", rejected.d5) == 1
    assert _count(db, "rejected_event_originals", later.d5) == 0
    assert _count(db, "operation_events", accepted.d5) == 1
    assert _count(db, "operation_events", rejected.d5) == 0
    assert _count(db, "operation_events", later.d5) == 0
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT confirmed_watermark FROM recording_generations "
            "WHERE tenant_id = %s AND game_id = %s AND generation = 1",
            (db.tenant_a, db.game_a),
        )
        assert cursor.fetchone() == (1,)
    db.catalog.applicator.rollback()


def test_lost_ack_replays_same_player_mapping(prefix_database: _SyncDatabase) -> None:
    """Commit 後の ACK 消失と引き継ぎ後の再送でも選手を二重生成しない。"""
    db = prefix_database
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT home_team_record_id FROM games WHERE tenant_id = %s AND id = %s",
            (db.tenant_a, db.game_a),
        )
        row = cursor.fetchone()
    db.catalog.applicator.rollback()
    assert row is not None
    temporary = uuid4()
    registration = PlayerRegistration(temporary, row[0], "同期登録選手", "active")
    event = _event(
        db.game_a,
        kind="player_registration",
        payload={"player_id": str(temporary)},
        d4="1",
    )
    request = SyncRequest("P1", str(db.game_a), (event,), d4="1", v12="proof")

    def lose_ack(point: CrashPoint) -> None:
        if point == "after_transaction":
            raise RuntimeError("ACK 消失")

    with _testing_crash_hook(lose_ack):
        with pytest.raises(RuntimeError, match="ACK 消失"):
            _invoke(db, request, registration=registration)
    transferred = SyncRequest(
        "P1", str(db.game_a), (event,), d4="1", v12="new-holder-proof"
    )
    no_longer_holder = DenyPrefixRights()
    replay = _invoke(
        db, transferred, registration=registration, rights=no_longer_holder
    )
    assert isinstance(replay, AckResult)
    assert (replay.boundary, replay.d3, replay.a5[0].state) == ("B1", 1, "重複")
    assert no_longer_holder.calls == []
    formal = UUID(replay.temporary_id_mapping[str(temporary)])
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM players WHERE tenant_id = %s AND id = %s",
            (db.tenant_a, formal),
        )
        player_count = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) FROM temporary_player_id_mappings "
            "WHERE tenant_id = %s AND temporary_id = %s AND player_id = %s",
            (db.tenant_a, temporary, formal),
        )
        mapping_count = cursor.fetchone()
    db.catalog.applicator.rollback()
    assert player_count == (1,) and mapping_count == (1,)
    assert _count(db, "operation_events", event.d5) == 1
    assert _count(db, "idempotency_ledger", event.d5) == 1


def test_other_tenant_and_missing_game_have_identical_b6(
    prefix_database: _SyncDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B6 は存在差を漏らさず、D5・記録権・行ロックを読まない。"""
    db = prefix_database
    seen: list[str] = []
    original = _TenantTransaction.run

    def spy(self: _TenantTransaction, token: TenantOperationToken):
        seen.append(type(token).__name__)
        return original(self, token)

    monkeypatch.setattr(_TenantTransaction, "run", spy)
    for game_id in (db.game_b, uuid4()):
        event = _event(game_id, d4="1")
        request = SyncRequest("P1", str(game_id), (event,), d4="1", v12="proof")
        rights = PrefixRights()
        seen.clear()
        assert _invoke(db, request, rights=rights) == "B6"
        assert seen == ["GameReadToken"]
        assert rights.calls == [] and rights.rg1_calls == []


@pytest.mark.parametrize("path", ["P1", "P3"])
def test_rg1_stop_from_public_entry_takes_no_row_locks(
    prefix_database: _SyncDatabase, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """③-a の B7/B10 は D5 と FOR UPDATE に先行し、D5 を消費しない。"""
    db = prefix_database
    request = (
        _change_request(db.game_a)
        if path == "P3"
        else SyncRequest(
            "P1",
            str(db.game_a),
            (_event(db.game_a, d4="1"),),
            d4="1",
            v12="proof",
        )
    )
    seen: list[str] = []
    original = _TenantTransaction.run

    def spy(self: _TenantTransaction, token: TenantOperationToken):
        seen.append(type(token).__name__)
        return original(self, token)

    monkeypatch.setattr(_TenantTransaction, "run", spy)
    rights = (
        ChangeRights(restoration=True)
        if path == "P3"
        else PrefixRights(read_open=False)
    )
    result = _invoke(db, request, rights=rights)
    if path == "P1":
        assert result == "B7"
    else:
        assert getattr(result, "boundary", None) == "B10"
    assert "GameLockToken" not in seen
    assert "RecordingGenerationLockToken" not in seen
    assert "IdempotencyLedgerReadToken" not in seen
    assert _count(db, "idempotency_ledger", request.events[0].d5) == 0


@pytest.mark.parametrize("path", ["P1", "P2", "P3", "P4", "P5"])
def test_public_entry_lock_order_including_d5_recheck(
    prefix_database: _SyncDatabase, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """P1〜P5 の実入口と再掲で、FOR UPDATE は試合行の次に世代行。"""
    db = prefix_database
    if path == "P3":
        seed = _event(db.game_a, d4="1")
        seed_request = SyncRequest("P1", str(db.game_a), (seed,), d4="1", v12="proof")
        assert isinstance(_invoke(db, seed_request), AckResult)
        _set_in_progress(db)
        request = _change_request(db.game_a)
    else:
        event = _event(db.game_a, d4="1")
        request = SyncRequest(
            "P4" if path == "P4" else "P2" if path == "P2" else "P1",
            str(db.game_a),
            (event,),
            d4="1",
            v12="proof",
        )
    seen: list[str] = []
    original = _TenantTransaction.run

    def spy(self: _TenantTransaction, token: TenantOperationToken):
        name = type(token).__name__
        if name in {"GameLockToken", "RecordingGenerationLockToken"}:
            seen.append(name)
        return original(self, token)

    monkeypatch.setattr(_TenantTransaction, "run", spy)
    for _ in range(2):
        seen.clear()
        result = _invoke(
            db,
            request,
            rights=DenyPrefixRights() if path == "P4" else None,
            reject=path == "P5",
        )
        assert result != "B6" and result != "B7"
        assert seen
        assert len(seen) % 2 == 0
        assert list(zip(seen[::2], seen[1::2], strict=True)) == [
            ("GameLockToken", "RecordingGenerationLockToken")
        ] * (len(seen) // 2)


_CRASH_CASES: tuple[tuple[str, CrashPoint], ...] = (
    ("P1", "before_transaction"),
    ("P1", "after_t1_ledger"),
    ("P1", "after_t6_result"),
    ("P1", "after_t2_event"),
    ("P1", "after_t3_prefix"),
    ("P1", "after_t4_projection"),
    ("P1-registration", "before_t6_mapping"),
    ("P1-registration", "after_t6_mapping"),
    ("P1", "after_transaction"),
    ("P2", "before_transaction"),
    ("P2", "after_t5_order"),
    ("P2", "after_t1_ledger"),
    ("P2", "after_t6_result"),
    ("P2", "after_t2_event"),
    ("P2", "after_t3_prefix"),
    ("P2", "after_t4_projection"),
    ("P2", "after_transaction"),
    ("P3", "before_transaction"),
    ("P3", "after_t1_ledger"),
    ("P3", "after_t6_result"),
    ("P3", "after_t2_event"),
    ("P3", "after_t4_projection"),
    ("P3", "after_t7_intents"),
    ("P3", "after_transaction"),
    ("P4", "before_transaction"),
    ("P4", "after_t8_ledger"),
    ("P4", "after_t8_original"),
    ("P4", "after_transaction"),
    ("P5", "before_transaction"),
    ("P5", "after_t9_ledger"),
    ("P5", "after_t9_original"),
    ("P5", "after_transaction"),
)


def test_mixed_batch_crash_replays_prefix_and_reapplies_remaining_events(
    prefix_database: _SyncDatabase,
) -> None:
    """P2/P1/P2 の途中で落ちても、再送は前方だけ再掲して残りを適用する。"""
    db = prefix_database
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT home_team_record_id FROM games WHERE tenant_id = %s AND id = %s",
            (db.tenant_a, db.game_a),
        )
        team = cursor.fetchone()
    db.catalog.applicator.rollback()
    assert team is not None
    temporary = uuid4()
    registration = PlayerRegistration(temporary, team[0], "途中停止登録", "active")
    first = _event(db.game_a, d1=1, d4="1", kind="play_input")
    middle = _event(
        db.game_a,
        d1=2,
        d4="1",
        kind="player_registration",
        payload={"player_id": str(temporary)},
    )
    last = _event(db.game_a, d1=3, d4="1", kind="game_end_declaration")
    batch = SyncEventBatch(str(db.game_a), "1", (last, middle, first), v12="proof")

    def crash(point: CrashPoint) -> None:
        if point == "after_t6_mapping":
            raise RuntimeError("混在バッチの途中で停止")

    with _testing_crash_hook(crash):
        with pytest.raises(RuntimeError, match="混在バッチの途中で停止"):
            _invoke_events(db, batch, registrations={2: registration})
    assert _count(db, "idempotency_ledger", first.d5) == 1
    assert _count(db, "operation_events", first.d5) == 1
    for event in (middle, last):
        assert _count(db, "idempotency_ledger", event.d5) == 0
        assert _count(db, "operation_events", event.d5) == 0

    replay = _invoke_events(db, batch, registrations={2: registration})
    assert (replay.boundary, replay.d3) == ("B1", 3)
    assert [(row.d1, row.state) for row in replay.a5] == [
        (1, "重複"),
        (2, "受理"),
        (3, "受理"),
    ]
    assert all(_count(db, "operation_events", event.d5) == 1 for event in batch.events)


@pytest.mark.parametrize(("path", "point"), _CRASH_CASES)
def test_named_crash_points_leave_whole_event_or_no_event(
    prefix_database: _SyncDatabase, path: str, point: CrashPoint
) -> None:
    """各経路の注入点で、対象 D5 の台帳とイベントが部分確定しない。"""
    db = prefix_database
    registration = None
    if path == "P3":
        seed = _event(db.game_a, d4="1")
        seed_request = SyncRequest("P1", str(db.game_a), (seed,), d4="1", v12="proof")
        assert isinstance(_invoke(db, seed_request), AckResult)
        _set_in_progress(db)
        request = _change_request(db.game_a)
    else:
        event = _event(db.game_a, d4="1")
        if path == "P1-registration":
            with db.catalog.applicator.cursor() as cursor:
                cursor.execute(
                    "SELECT home_team_record_id FROM games "
                    "WHERE tenant_id = %s AND id = %s",
                    (db.tenant_a, db.game_a),
                )
                row = cursor.fetchone()
            db.catalog.applicator.rollback()
            assert row is not None
            temporary = uuid4()
            registration = PlayerRegistration(temporary, row[0], "注入選手", "active")
            event = _event(
                db.game_a,
                d4="1",
                kind="player_registration",
                payload={"player_id": str(temporary)},
            )
        request = SyncRequest(
            "P4" if path == "P4" else "P2" if path == "P2" else "P1",
            str(db.game_a),
            (event,),
            d4="1",
            v12="proof",
        )
    observed: list[CrashPoint] = []
    before = _game_state(db)

    def crash(name: CrashPoint) -> None:
        observed.append(name)
        if name == point:
            raise RuntimeError("注入した電源断")

    with _testing_crash_hook(crash):
        with pytest.raises(RuntimeError, match="注入した電源断"):
            _invoke(
                db,
                request,
                registration=registration,
                rights=DenyPrefixRights() if path == "P4" else None,
                reject=path == "P5",
            )
    assert point in observed
    expected = 1 if point == "after_transaction" else 0
    assert _count(db, "idempotency_ledger", request.events[0].d5) == expected
    assert _count(db, "operation_events", request.events[0].d5) == (
        expected if path in {"P1", "P2", "P3", "P1-registration"} else 0
    )
    assert _count(db, "rejected_event_originals", request.events[0].d5) == (
        expected if path == "P5" else 0
    )
    assert _count(db, "evacuated_event_originals", request.events[0].d5) == (
        expected if path == "P4" else 0
    )
    after = _game_state(db)
    assert after[0] == before[0] + (
        expected if path in {"P1", "P2", "P1-registration"} else 0
    )
    assert after[1] == before[1] + (
        5 * expected if path in {"P1", "P2", "P3", "P1-registration"} else 0
    )
    if registration is not None:
        with db.catalog.applicator.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM temporary_player_id_mappings "
                "WHERE tenant_id = %s AND temporary_id = %s",
                (db.tenant_a, registration.temporary_id),
            )
            mapped = cursor.fetchone()
            cursor.execute(
                "SELECT count(*) FROM players WHERE tenant_id = %s AND name = %s",
                (db.tenant_a, registration.name),
            )
            players = cursor.fetchone()
        db.catalog.applicator.rollback()
        assert mapped == (expected,)
        # 写像の保存前に落ちても、選手行だけが残ることはない(全部確定か全部未確定)。
        assert players == (expected,)
