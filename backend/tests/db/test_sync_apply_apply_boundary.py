"""公開入口の ACK、非開示、R-16、各 T 境界を使い捨て DB で確かめる。"""

from __future__ import annotations

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

from pitchlog.repositories.tokens import TenantOperationToken
from pitchlog.repositories.transaction import (
    _TenantTransaction,
    tenant_transaction_scope,
)
from pitchlog.sync import ports
from pitchlog.sync.apply import apply_sync_request
from pitchlog.sync.crash_points import CrashPoint
from pitchlog.sync.crash_points import testing_crash_hook as _testing_crash_hook
from pitchlog.sync.model import AckResult, SyncEvent, SyncRequest
from pitchlog.sync.prefix_path import PlayerRegistration
from pitchlog.sync.tokens import IdempotencyLedgerInsertToken

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
        registrations={request.events[0].d5: registration} if registration else None,
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
        db.catalog.applicator.rollback()
        assert mapped == (expected,)
