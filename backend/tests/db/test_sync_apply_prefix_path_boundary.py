"""P1 の一イベント境界を使い捨て製品 DB で確認する。"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
from test_authz_tenant_context import make_tenant_context
from test_sync_apply_port_prefix import (
    DenyPrefixRights,
    PrefixProjection,
    PrefixRights,
    PrefixValidator,
    ScopeOpeningProjection,
)

from pitchlog.repositories.transaction import tenant_transaction_scope
from pitchlog.sync import ports
from pitchlog.sync.idempotency import _json_value, source_fingerprint
from pitchlog.sync.model import ABSENT, SyncEvent
from pitchlog.sync.prefix_path import (
    P1PreconditionError,
    P1Result,
    P1Target,
    PlayerRegistration,
    apply_p1_event,
)
from pitchlog.sync.tokens import (
    IdempotencyLedgerInsertToken,
    RejectedOriginalInsertToken,
)

from .test_sync_apply_operations_boundary import _SyncDatabase, sync_database

__all__ = ("sync_database",)

pytestmark = pytest.mark.requires_db


@pytest.fixture
def prefix_database(sync_database: _SyncDatabase) -> _SyncDatabase:
    """操作登録試験の既存スロットとは別に、空の D1 を持つ試合を作る。"""
    game_id = uuid4()
    with sync_database.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO games (tenant_id, id, scheduled_at, game_type_key, "
            "tournament_key, away_team_record_id, home_team_record_id, applied_rules) "
            "SELECT tenant_id, %s, scheduled_at, game_type_key, "
            "tournament_key, away_team_record_id, home_team_record_id, applied_rules "
            "FROM games WHERE tenant_id = %s AND id = %s",
            (game_id, sync_database.tenant_a, sync_database.game_a),
        )
        cursor.execute(
            "INSERT INTO recording_generations (tenant_id, game_id, generation, "
            "kind, issuance_order, holder_device) "
            "VALUES (%s, %s, 1, 'normal', 1, 'test-device')",
            (sync_database.tenant_a, game_id),
        )
    sync_database.catalog.applicator.commit()
    return _SyncDatabase(
        sync_database.catalog,
        sync_database.tenant_a,
        sync_database.tenant_b,
        game_id,
        sync_database.game_b,
    )


@pytest.fixture(autouse=True)
def _register_synthetic_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    """合成ポートだけをテスト中に登録し、製品の空表は保つ。"""
    monkeypatch.setattr(
        ports,
        "PORT_IMPLEMENTATIONS",
        frozenset(
            (cls.__module__, cls.__name__)
            for cls in (
                PrefixRights,
                DenyPrefixRights,
                PrefixValidator,
                PrefixProjection,
                ScopeOpeningProjection,
            )
        ),
    )


def _event(
    game: UUID,
    *,
    d1: int = 1,
    kind: str = "game_end_declaration",
    tombstone: bool = False,
    revision: bool = False,
    d5: UUID | None = None,
    rejected_d5: UUID | None = None,
    payload: dict[str, object] | None = None,
    d4: str = "epoch",
) -> SyncEvent:
    """DDL の D1 付き参加区分を満たす P1 イベントを作る。"""
    return SyncEvent(
        str(d5 or uuid4()),
        str(game),
        d1,
        d4,
        v5=kind,
        v6=d1 * 10 if not tombstone and kind == "game_end_declaration" else ABSENT,
        v7={} if payload is None else payload,
        v9=(
            {"tombstone": True, "rejected_d5": str(rejected_d5)}
            if tombstone
            else {"revision": True, "rejected_d5": str(rejected_d5)}
            if revision
            else ABSENT
        ),
        v10=(
            {"game": str(game), "d4": d4, "d1": d1} if tombstone or revision else ABSENT
        ),
    )


def _apply(
    db: _SyncDatabase,
    event: SyncEvent,
    *,
    tenant: UUID | None = None,
    rights: PrefixRights | DenyPrefixRights | None = None,
    registration: PlayerRegistration | None = None,
    projection: PrefixProjection | ScopeOpeningProjection | None = None,
    target: P1Target | None = None,
) -> tuple[P1Result, PrefixProjection | ScopeOpeningProjection]:
    """一件を本物の製品 scope と合成ポートで適用する。"""
    selected = projection or PrefixProjection()
    result = apply_p1_event(
        make_tenant_context(tenant or db.tenant_a),
        event,
        rights or PrefixRights(),
        selected,
        PrefixValidator(),
        "proof",
        registration=registration,
        target=target,
    )
    return result, selected


def _reject_original(
    db: _SyncDatabase, event: SyncEvent, *, tenant: UUID | None = None
) -> None:
    """T9 と同じ D5・試合・D4・D1 を持つ内容拒否原本を保存する。"""
    source: dict[str, object] = {
        "d5": event.d5,
        "game_id": event.game_id,
        "d4": event.d4,
        "d1": event.d1,
        "event_kind": event.v5,
        "payload": event.v7,
    }
    if event.v6 is not ABSENT:
        source["d2"] = event.v6
    with tenant_transaction_scope(make_tenant_context(tenant or db.tenant_a)) as scope:
        scope.run(
            IdempotencyLedgerInsertToken(
                UUID(event.d5),
                "rejected",
                source_fingerprint(source),
                '{"state":"拒否"}',
                "内容拒否",
            )
        )
        scope.run(
            RejectedOriginalInsertToken(
                uuid4(),
                UUID(event.d5),
                json.dumps(_json_value(source), ensure_ascii=False),
            )
        )


def _snapshot(db: _SyncDatabase, game: UUID) -> tuple[int, int, int, int]:
    """確定水位・イベント・台帳・意図の数を独立 SQL で読む。"""
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT confirmed_watermark FROM recording_generations "
            "WHERE tenant_id = %s AND game_id = %s AND generation = 1",
            (db.tenant_a, game),
        )
        row = cursor.fetchone()
        assert row is not None
        d3 = row[0]
        cursor.execute(
            "SELECT count(*) FROM operation_events "
            "WHERE tenant_id = %s AND game_id = %s",
            (db.tenant_a, game),
        )
        row = cursor.fetchone()
        assert row is not None
        event_count = row[0]
        cursor.execute(
            "SELECT count(*) FROM idempotency_ledger WHERE tenant_id = %s",
            (db.tenant_a,),
        )
        row = cursor.fetchone()
        assert row is not None
        ledger_count = row[0]
        cursor.execute(
            "SELECT count(*) FROM invalidation_intents WHERE tenant_id = %s",
            (db.tenant_a,),
        )
        row = cursor.fetchone()
        assert row is not None
        intent_count = row[0]
    db.catalog.applicator.rollback()
    return d3, event_count, ledger_count, intent_count


def test_tombstone_advances_d3_and_replay_does_not_duplicate_intents(
    prefix_database: _SyncDatabase,
) -> None:
    """墓標で D3 を越え、T1/T6・T2・T3・I5 を同時に確定する。"""
    db = prefix_database
    rejected = _event(db.game_a)
    _reject_original(db, rejected)
    event = _event(db.game_a, tombstone=True, rejected_d5=UUID(rejected.d5))
    first, projection = _apply(db, event)
    assert first.accepted and not first.replayed
    assert isinstance(projection, PrefixProjection)
    assert len(projection.events) == 1
    assert _snapshot(db, db.game_a) == (1, 1, 2, 5)
    again, replay_projection = _apply(db, event)
    assert again.replayed and again.d3 == first.d3
    assert isinstance(replay_projection, PrefixProjection)
    assert replay_projection.events == []
    assert _snapshot(db, db.game_a) == (1, 1, 2, 5)
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT is_tombstone, payload FROM operation_events "
            "WHERE tenant_id = %s AND game_id = %s",
            (db.tenant_a, db.game_a),
        )
        assert cursor.fetchone() == (True, {})
        cursor.execute(
            "SELECT intent_id FROM invalidation_intents WHERE tenant_id = %s",
            (db.tenant_a,),
        )
        assert {row[0] for row in cursor.fetchall()} == {
            f"sync:{event.d5}:{kind}"
            for kind in ("game", "player_total", "team_total", "shared_total", "chart")
        }
    db.catalog.applicator.rollback()


def test_revision_does_not_regress_d3_and_rejected_position_advances(
    prefix_database: _SyncDatabase,
) -> None:
    """内容拒否の D1 の改訂だけが水位を前進させる。"""
    db = prefix_database
    original = _event(db.game_a)
    first, _ = _apply(db, original)
    assert first.d3 == 1
    rejected = _event(db.game_a, d1=2)
    _reject_original(db, rejected)
    assert _snapshot(db, db.game_a) == (1, 1, 2, 5)
    revised = _event(db.game_a, d1=2, revision=True, rejected_d5=UUID(rejected.d5))
    second, _ = _apply(db, revised)
    assert second.d3 == 2
    assert _snapshot(db, db.game_a) == (2, 2, 3, 10)
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT is_tombstone FROM operation_events WHERE tenant_id = %s "
            "AND game_id = %s AND d1 = 2 AND replaced_at IS NULL",
            (db.tenant_a, db.game_a),
        )
        assert cursor.fetchone() == (False,)
    db.catalog.applicator.rollback()


@pytest.mark.parametrize("kind", ["tombstone", "revision"])
def test_replacement_without_matching_rejected_original_is_refused(
    prefix_database: _SyncDatabase, kind: str
) -> None:
    """T9 の原本がない D1 は墓標・改訂のどちらでも消費できない。"""
    db = prefix_database
    event = _event(
        db.game_a,
        tombstone=kind == "tombstone",
        revision=kind == "revision",
        rejected_d5=uuid4(),
    )
    with pytest.raises(P1PreconditionError, match="対応する内容拒否"):
        _apply(db, event)
    assert _snapshot(db, db.game_a) == (0, 0, 0, 0)


@pytest.mark.parametrize("kind", ["tombstone", "revision"])
def test_replacement_requires_v10(prefix_database: _SyncDatabase, kind: str) -> None:
    """拒否原本の D5 が正しくても対象 V10 の欠落を許さない。"""
    db = prefix_database
    rejected = _event(db.game_a)
    _reject_original(db, rejected)
    replacement = SyncEvent(
        str(uuid4()),
        str(db.game_a),
        1,
        "epoch",
        v5="game_end_declaration",
        v6=ABSENT if kind == "tombstone" else 10,
        v7={},
        v9={kind: True, "rejected_d5": rejected.d5},
    )
    with pytest.raises(P1PreconditionError, match="V10 の対象参照") as error:
        _apply(db, replacement)
    assert error.value.category == "w2_violation"
    assert _snapshot(db, db.game_a) == (0, 0, 1, 0)


def test_replacement_cannot_target_accepted_other_d1(
    prefix_database: _SyncDatabase,
) -> None:
    """V10 を別の確定済み D1 へ向けても拒否原本を流用できない。"""
    db = prefix_database
    _apply(db, _event(db.game_a))
    rejected = _event(db.game_a, d1=2)
    _reject_original(db, rejected)
    replacement = SyncEvent(
        str(uuid4()),
        str(db.game_a),
        2,
        "epoch",
        v5="game_end_declaration",
        v6=20,
        v7={},
        v9={"revision": True, "rejected_d5": rejected.d5},
        v10={"game": str(db.game_a), "d4": "epoch", "d1": 1},
    )
    with pytest.raises(P1PreconditionError, match="V10 が置換する D1") as error:
        _apply(db, replacement)
    assert error.value.category == "w2_violation"
    assert _snapshot(db, db.game_a) == (1, 1, 2, 5)


def test_replacement_rejects_original_from_other_game_in_same_tenant(
    prefix_database: _SyncDatabase, sync_database: _SyncDatabase
) -> None:
    """同じテナントでも、別試合の T9 原本は流用できない。"""
    db = prefix_database
    rejected = _event(sync_database.game_a)
    _reject_original(db, rejected)
    replacement = _event(db.game_a, revision=True, rejected_d5=UUID(rejected.d5))
    with pytest.raises(P1PreconditionError, match="置換対象と一致しない") as error:
        _apply(db, replacement)
    assert error.value.category == "w2_violation"
    assert _snapshot(db, db.game_a) == (0, 0, 1, 0)


def test_replacement_rejects_original_from_other_d4(
    prefix_database: _SyncDatabase,
) -> None:
    """同じ試合の旧 D4 の T9 原本を現 D4 へ流用しない。"""
    db = prefix_database
    rejected = _event(db.game_a, d4="older-epoch")
    _reject_original(db, rejected)
    replacement = _event(db.game_a, revision=True, rejected_d5=UUID(rejected.d5))
    with pytest.raises(P1PreconditionError, match="置換対象と一致しない") as error:
        _apply(db, replacement)
    assert error.value.category == "w2_violation"
    assert _snapshot(db, db.game_a) == (0, 0, 1, 0)


def test_replacement_cannot_read_other_tenant_rejected_original(
    prefix_database: _SyncDatabase,
) -> None:
    """他テナントの T9 原本は存在を判別できず、置換も残さない。"""
    db = prefix_database
    rejected = _event(db.game_b)
    _reject_original(db, rejected, tenant=db.tenant_b)
    replacement = _event(db.game_a, revision=True, rejected_d5=UUID(rejected.d5))
    with pytest.raises(
        P1PreconditionError, match="対応する内容拒否の D5 がない"
    ) as error:
        _apply(db, replacement)
    assert error.value.category == "w2_violation"
    assert _snapshot(db, db.game_a) == (0, 0, 0, 0)


def test_replacement_cannot_consume_other_rejected_position(
    prefix_database: _SyncDatabase,
) -> None:
    """別 D1 の T9 原本を V9 に指定しても通さない。"""
    db = prefix_database
    rejected = _event(db.game_a, d1=2)
    _reject_original(db, rejected)
    replacement = _event(db.game_a, revision=True, rejected_d5=UUID(rejected.d5))
    with pytest.raises(P1PreconditionError, match="D1 が置換対象と一致しない"):
        _apply(db, replacement)
    assert _snapshot(db, db.game_a) == (0, 0, 1, 0)


def test_revision_keeps_rejected_original_logical_position(
    prefix_database: _SyncDatabase,
) -> None:
    """改訂で拒否原本の D2 を別位置へ付け替えない。"""
    db = prefix_database
    rejected = _event(db.game_a)
    _reject_original(db, rejected)
    revision = SyncEvent(
        str(uuid4()),
        str(db.game_a),
        1,
        "epoch",
        v5="game_end_declaration",
        v6=999,
        v7={},
        v9={"revision": True, "rejected_d5": rejected.d5},
    )
    with pytest.raises(P1PreconditionError, match="D2 を継承"):
        _apply(db, revision)
    assert _snapshot(db, db.game_a) == (0, 0, 1, 0)


def test_accepted_event_cannot_be_revised(
    prefix_database: _SyncDatabase,
) -> None:
    """W2: 受理済みの D5 を拒否原本と詐称して改訂しない。"""
    db = prefix_database
    accepted = _event(db.game_a)
    _apply(db, accepted)
    revision = _event(db.game_a, revision=True, rejected_d5=UUID(accepted.d5))
    with pytest.raises(P1PreconditionError, match="確定済み D1"):
        _apply(db, revision)
    assert _snapshot(db, db.game_a) == (1, 1, 1, 5)


def test_v9_cannot_claim_both_replacement_kinds(
    prefix_database: _SyncDatabase,
) -> None:
    """V9 の値が種別を一意に決めない入力を拒否する。"""
    db = prefix_database
    ambiguous = SyncEvent(
        str(uuid4()),
        str(db.game_a),
        1,
        "epoch",
        v5="game_end_declaration",
        v7={},
        v9={"revision": True, "tombstone": True, "rejected_d5": str(uuid4())},
    )
    with pytest.raises(P1PreconditionError, match="V9 の置換種別"):
        _apply(db, ambiguous)
    assert _snapshot(db, db.game_a) == (0, 0, 0, 0)


def test_recording_right_is_checked_before_gap(
    prefix_database: _SyncDatabase,
) -> None:
    """未使用 D5 では記録権を拒否してから初めて B2 を判定する。"""
    db = prefix_database
    rights = DenyPrefixRights()
    with pytest.raises(P1PreconditionError, match="記録権不一致"):
        _apply(db, _event(db.game_a, d1=3), rights=rights)
    assert rights.calls == [str(db.game_a)]
    assert _snapshot(db, db.game_a) == (0, 0, 0, 0)


def test_player_registration_mapping_is_saved_and_replayed(
    prefix_database: _SyncDatabase,
) -> None:
    """U-M1 の選手行と別表の写像を保存し、再送では同じ ID を返す。"""
    db = prefix_database
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT home_team_record_id FROM games WHERE tenant_id = %s AND id = %s",
            (db.tenant_a, db.game_a),
        )
        row = cursor.fetchone()
        assert row is not None
        team_id = row[0]
    db.catalog.applicator.rollback()
    temporary = uuid4()
    registration = PlayerRegistration(temporary, team_id, "その場登録選手", "active")
    event = _event(
        db.game_a,
        kind="player_registration",
        payload={"player_id": str(temporary)},
    )
    first, projection = _apply(db, event, registration=registration)
    assert first.accepted and len(first.temporary_id_mapping) == 1
    formal = UUID(first.temporary_id_mapping[0][1])
    assert isinstance(projection, PrefixProjection)
    assert projection.events[0].v7 == {"player_id": str(formal)}
    replay, later_projection = _apply(db, event, registration=registration)
    assert replay.replayed
    assert replay.temporary_id_mapping == first.temporary_id_mapping
    assert isinstance(later_projection, PrefixProjection)
    assert later_projection.events == []
    following = _event(db.game_a, d1=2, payload={"player_id": str(temporary)})
    next_result, next_projection = _apply(db, following)
    assert next_result.accepted and next_result.d3 == 2
    assert isinstance(next_projection, PrefixProjection)
    assert next_projection.events[0].v7 == {"player_id": str(formal)}
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT player_id FROM temporary_player_id_mappings "
            "WHERE tenant_id = %s AND temporary_id = %s",
            (db.tenant_a, temporary),
        )
        assert cursor.fetchall() == [(formal,)]
        cursor.execute(
            "SELECT payload FROM operation_events WHERE tenant_id = %s "
            "AND game_id = %s AND d1 = 2",
            (db.tenant_a, db.game_a),
        )
        assert cursor.fetchall() == [({"player_id": str(formal)},)]
        cursor.execute(
            "SELECT count(*) FROM players WHERE tenant_id = %s AND id = %s",
            (db.tenant_a, formal),
        )
        row = cursor.fetchone()
        assert row is not None and row[0] == 1
    db.catalog.applicator.rollback()


def test_undo_persists_resolved_target_slot(prefix_database: _SyncDatabase) -> None:
    """V10 の対象を試合・世代・D1 の組としてイベント行へ保存する。"""
    db = prefix_database
    _apply(db, _event(db.game_a))
    target = P1Target(db.game_a, 1, 1)
    undo = SyncEvent(
        str(uuid4()),
        str(db.game_a),
        2,
        "epoch",
        v5="undo",
        v7={},
        v10={"game": str(db.game_a), "d4": "epoch", "d1": 1},
    )
    outcome, _ = _apply(db, undo, target=target)
    assert outcome.accepted and outcome.d3 == 2
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT target_generation, target_d1 FROM operation_events "
            "WHERE tenant_id = %s AND d5 = %s",
            (db.tenant_a, UUID(undo.d5)),
        )
        assert cursor.fetchall() == [(1, 1)]
    db.catalog.applicator.rollback()


def test_unresolved_temporary_player_reference_is_not_committed(
    prefix_database: _SyncDatabase,
) -> None:
    """C2 の未解決参照は元の一時 ID のまま保存しない。"""
    db = prefix_database
    temporary = uuid4()
    event = _event(db.game_a, payload={"player_id": str(temporary)})
    with pytest.raises(P1PreconditionError, match="確定写像がない"):
        _apply(db, event)
    assert _snapshot(db, db.game_a) == (0, 0, 0, 0)


def test_port_opening_own_scope_is_rejected_after_call_and_rolls_back(
    prefix_database: _SyncDatabase,
) -> None:
    """投影が呼ばれてから同じスレッドの別 scope を拒否し、全書込を戻す。"""
    db = prefix_database
    calls: list[str] = []

    def open_scope() -> None:
        calls.append("port_called")
        try:
            with tenant_transaction_scope(make_tenant_context(db.tenant_a)):
                pass
        except RuntimeError:
            calls.append("scope_rejected")
            raise

    projection = ScopeOpeningProjection(open_scope)
    with pytest.raises(RuntimeError, match="同期適用中に新しいテナントスコープ"):
        _apply(db, _event(db.game_a), projection=projection)
    assert projection.calls == 1
    assert calls == ["port_called", "scope_rejected"]
    assert _snapshot(db, db.game_a) == (0, 0, 0, 0)
