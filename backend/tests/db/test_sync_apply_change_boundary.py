"""P3 の原子境界と同期意図の再配送を使い捨て製品 DB で検査する。"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from uuid import UUID, uuid4

import pytest
from test_authz_tenant_context import make_tenant_context
from test_sync_apply_port_change import (
    ChangeProjection,
    ChangeRights,
    ChangeSink,
    ChangeValidator,
)

from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.tokens import TenantOperationToken
from pitchlog.repositories.transaction import (
    _TenantTransaction,
    tenant_transaction_scope,
)
from pitchlog.sync import invalidation, ports
from pitchlog.sync.change_path import apply_p3_change
from pitchlog.sync.model import ABSENT, SyncEvent, SyncRequest

from .test_sync_apply_operations_boundary import _SyncDatabase

pytestmark = pytest.mark.requires_db
pytest_plugins = ("db.test_sync_apply_operations_boundary",)
_KINDS = ("game", "player_total", "team_total", "shared_total", "chart")


@pytest.fixture(autouse=True)
def _register_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    """製品の登録表は変えず、この試験中だけ合成ポートを接続する。"""
    monkeypatch.setattr(
        ports,
        "PORT_IMPLEMENTATIONS",
        frozenset(
            (cls.__module__, cls.__name__)
            for cls in (ChangeRights, ChangeProjection, ChangeValidator, ChangeSink)
        ),
    )


def _set_status(db: _SyncDatabase, status: str) -> None:
    """テスト試合を P3 が処理する状態に置く。"""
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "UPDATE games SET status = %s WHERE tenant_id = %s AND id = %s",
            (status, db.tenant_a, db.game_a),
        )
    db.catalog.applicator.commit()


def _request(
    game_id: UUID,
    *,
    d5: UUID | None = None,
    expected_version: object = 1,
    payload: object = None,
    kind: str = "play_change",
    v12: object = "proof",
) -> SyncRequest:
    """種別ごとの CHECK を満たす P3 原本を作る。"""
    event = SyncEvent(
        str(d5 or uuid4()),
        str(game_id),
        v5=kind,
        v7={"change": "first"} if payload is None else payload,
        v10={"game": str(game_id), "d4": 1, "d1": 1},
        v11=expected_version,
    )
    return SyncRequest(
        "P3", str(game_id), (event,), recovery_generation="current", v12=v12
    )


def _apply(
    db: _SyncDatabase,
    request: SyncRequest,
    rights: ChangeRights | None = None,
    projection: ChangeProjection | None = None,
    validator: ChangeValidator | None = None,
):
    """認可済み A の文脈で局所 P3 を実行する。"""
    return apply_p3_change(
        make_tenant_context(db.tenant_a),
        request,
        rights or ChangeRights(),
        projection or ChangeProjection(),
        validator or ChangeValidator(),
    )


def _counts(db: _SyncDatabase, d5: UUID) -> tuple[int, int, int, int]:
    """台帳・変更イベント・意図・対象版を別々の行で観測する。"""
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM idempotency_ledger WHERE tenant_id = %s AND d5 = %s",
            (db.tenant_a, d5),
        )
        ledger = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) FROM operation_events WHERE tenant_id = %s AND d5 = %s",
            (db.tenant_a, d5),
        )
        events = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) FROM invalidation_intents WHERE tenant_id = %s",
            (db.tenant_a,),
        )
        intents = cursor.fetchone()
        cursor.execute(
            "SELECT confirmed_version FROM event_slots WHERE tenant_id = %s "
            "AND game_id = %s AND generation = 1 AND d1 = 1",
            (db.tenant_a, db.game_a),
        )
        slot = cursor.fetchone()
    assert ledger and events and intents and slot
    return ledger[0], events[0], intents[0], slot[0]


def test_p3_acceptance_replay_intents_and_lock_order(
    sync_database: _SyncDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T1/T2/T4/T6/T7 の確定、五つの ID、再掲、R-16 の順を観測する。"""
    db = sync_database
    _set_status(db, "in_progress")
    request = _request(db.game_a)
    observed: list[str] = []
    original = _TenantTransaction.run

    def spy(self: _TenantTransaction, token: TenantOperationToken):
        observed.append(type(token).__name__)
        return original(self, token)

    monkeypatch.setattr(_TenantTransaction, "run", spy)
    projection, validator = ChangeProjection(), ChangeValidator()
    first = _apply(db, request, projection=projection, validator=validator)
    assert first.boundary == "変更受理"
    assert first.target_reference == {
        "試合": str(db.game_a),
        "対象の D4": 1,
        "対象の D1": 1,
    }
    assert first.expected_version == 1
    assert first.d5 == request.events[0].d5
    assert first.confirmed_content == {"change": "first"}
    assert first.accepted_at
    assert _counts(db, UUID(request.events[0].d5)) == (1, 1, 5, 2)
    assert len(projection.events) == 1
    assert observed.index("GameLockToken") < observed.index(
        "RecordingGenerationLockToken"
    )
    identity = f"{db.game_a}:1:1:2"
    expected_ids = {f"sync:{identity}:{kind}" for kind in _KINDS}
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT intent_id FROM invalidation_intents WHERE tenant_id = %s",
            (db.tenant_a,),
        )
        assert {row[0] for row in cursor.fetchall()} == expected_ids
    replay = _apply(db, request, projection=projection, validator=validator)
    assert replay == first
    assert _counts(db, UUID(request.events[0].d5)) == (1, 1, 5, 2)
    assert len(projection.events) == 1
    assert validator.calls == 1
    _set_status(db, "hidden")
    assert _apply(db, request, projection=projection, validator=validator) == first
    assert _counts(db, UUID(request.events[0].d5)) == (1, 1, 5, 2)


@pytest.mark.parametrize(
    "branch",
    ("B8", "B9-recovery", "B9-proof", "B10", "B12", "B13", "B14"),
)
def test_p3_rejected_branches_do_not_write(
    sync_database: _SyncDatabase, branch: str
) -> None:
    """B8〜B10・B12〜B14 は D5 と変更行と意図を残さない。"""
    db = sync_database
    _set_status(db, "in_progress")
    rights = ChangeRights(
        restoration=branch == "B10",
        current=branch != "B9-recovery",
        holds=branch != "B9-proof",
    )
    validator = ChangeValidator(valid=branch != "B14")
    request = _request(
        db.game_b if branch == "B12" else db.game_a,
        expected_version=2 if branch == "B8" else 1,
    )
    if branch == "B13":
        first = _apply(db, request)
        assert first.boundary == "変更受理"
        before = _counts(db, UUID(request.events[0].d5))
        request = _request(
            db.game_a, d5=UUID(request.events[0].d5), payload={"change": "other"}
        )
    else:
        before = _counts(db, UUID(request.events[0].d5))
    result = _apply(db, request, rights=rights, validator=validator)
    assert result.boundary == branch.split("-")[0]
    assert _counts(db, UUID(request.events[0].d5)) == before
    if branch == "B12":
        assert rights.calls == []
    elif branch not in ("B10",):
        assert "rg1_commit" not in rights.calls


@pytest.mark.parametrize("closed", [False, True])
def test_p3_other_tenant_and_missing_game_have_same_b12_before_rg1(
    sync_database: _SyncDatabase, closed: bool
) -> None:
    """他テナントと不存在は RG1 状態に依存せず同じ B12 を返す。"""
    db = sync_database
    d5 = uuid4()
    context = make_tenant_context(db.tenant_a)
    results = []
    for game_id in (db.game_b, uuid4()):
        rights = ChangeRights(restoration=closed, fail_at="read" if closed else None)
        result = apply_p3_change(
            context,
            _request(game_id, d5=d5),
            rights,
            ChangeProjection(),
            ChangeValidator(),
        )
        results.append(result)
        assert rights.calls == []
    assert results[0] == results[1]
    assert results[0].boundary == "B12"
    assert _counts(db, d5) == (0, 0, 0, 1)


def test_finished_p3_ignores_v12(sync_database: _SyncDatabase) -> None:
    """W4: 終了後は復旧世代を照合し、V12 の照合はしない。"""
    db = sync_database
    _set_status(db, "finished")
    rights = ChangeRights(holds=False)
    result = _apply(db, _request(db.game_a, v12=ABSENT), rights=rights)
    assert result.boundary == "変更受理"
    assert "holds" not in rights.calls


@pytest.mark.parametrize("failure", ["closed", "error"])
def test_restoration_started_before_commit_rolls_back_all_t_elements(
    sync_database: _SyncDatabase,
    failure: str,
) -> None:
    """RG1 のコミット前再照合で T1・T2・T7 と対象版をまとめて戻す。"""
    db = sync_database
    _set_status(db, "in_progress")
    request = _request(db.game_a)
    rights = ChangeRights(
        restoration_after_first=failure == "closed",
        fail_at="commit" if failure == "error" else None,
    )
    assert _apply(db, request, rights=rights).boundary == "B10"
    assert rights.calls.count("rg1_read") == 1
    assert rights.calls.count("rg1_commit") == 1
    assert _counts(db, UUID(request.events[0].d5)) == (0, 0, 0, 1)


def test_p3_saved_result_is_blocked_by_rg1(
    sync_database: _SyncDatabase,
) -> None:
    """保存済みの P3 も③-a が閉じていれば B10 で止める。"""
    db = sync_database
    _set_status(db, "in_progress")
    request = _request(db.game_a)
    assert _apply(db, request).boundary == "変更受理"
    rights = ChangeRights(restoration=True)
    assert _apply(db, request, rights=rights).boundary == "B10"
    assert rights.calls == ["rg1_read"]
    assert _counts(db, UUID(request.events[0].d5)) == (1, 1, 5, 2)


def test_internal_delivery_waits_while_rg1_is_closed(
    sync_database: _SyncDatabase,
) -> None:
    """内部配信は③-a で延期し、配信先も完了列も変更しない。"""
    db = sync_database
    _set_status(db, "in_progress")
    assert _apply(db, _request(db.game_a)).boundary == "変更受理"
    sink = ChangeSink()
    rights = ChangeRights(restoration=True)
    progress = invalidation.deliver_pending_sync_intents(
        make_tenant_context(db.tenant_a), sink, rights
    )
    assert progress == invalidation.DeliveryProgress(0, 0)
    assert rights.calls == ["rg1_read"]
    assert sink.calls == []
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM invalidation_intents "
            "WHERE tenant_id = %s AND delivery_status = 'pending'",
            (db.tenant_a,),
        )
        pending = cursor.fetchone()
    assert pending is not None and pending[0] == 5


def test_delivery_retries_same_id_after_crash_and_skips_b06(
    sync_database: _SyncDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """配信済み・完了記録前のクラッシュ後も同じ ID で論理効果を一度に保つ。"""
    db = sync_database
    _set_status(db, "in_progress")
    accepted = _apply(db, _request(db.game_a))
    assert accepted.boundary == "変更受理"
    other_id = f"14:{uuid4()}:game"
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO invalidation_intents "
            "(tenant_id, intent_id, scope_kind, game_id) "
            "VALUES (%s, %s, 'game', %s)",
            (db.tenant_a, other_id, db.game_a),
        )
    db.catalog.applicator.commit()
    context = make_tenant_context(db.tenant_a)
    sink = ChangeSink()
    real_scope = tenant_transaction_scope
    calls = 0

    @contextmanager
    def crash_before_completion(
        tenant: TenantContext,
    ) -> Iterator[_TenantTransaction]:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("配信先の消費後・完了記録前にクラッシュ")
        with real_scope(tenant) as scope:
            yield scope

    with monkeypatch.context() as mutation:
        mutation.setattr(
            invalidation, "tenant_transaction_scope", crash_before_completion
        )
        with pytest.raises(RuntimeError, match="完了記録前"):
            invalidation.deliver_pending_sync_intents(
                context, sink, ChangeRights(), page_size=2
            )
    assert len(sink.effects) == 1
    progress = invalidation.deliver_pending_sync_intents(
        context, sink, ChangeRights(), page_size=2
    )
    assert progress.delivered == 5
    assert len(sink.effects) == 5
    assert len(sink.calls) == 6
    assert other_id not in sink.calls
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT intent_id, delivery_status, delivered_at "
            "FROM invalidation_intents "
            "WHERE tenant_id = %s",
            (db.tenant_a,),
        )
        rows = cursor.fetchall()
    statuses = {key: status for key, status, _ in rows}
    completed_at = {key: timestamp for key, _, timestamp in rows}
    assert statuses[other_id] == "pending"
    assert all(
        status == "delivered" for key, status in statuses.items() if key != other_id
    )
    assert all(
        timestamp is not None
        for key, timestamp in completed_at.items()
        if key != other_id
    )
    calls_before = len(sink.calls)
    assert invalidation.deliver_pending_sync_intents(
        context, sink, ChangeRights(), page_size=2
    ) == invalidation.DeliveryProgress(0, 0)
    assert len(sink.calls) == calls_before
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT intent_id, delivered_at FROM invalidation_intents "
            "WHERE tenant_id = %s",
            (db.tenant_a,),
        )
        assert dict(cursor.fetchall()) == completed_at
