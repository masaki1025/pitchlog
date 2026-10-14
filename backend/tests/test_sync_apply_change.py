"""P3 の値境界と配信のページ走査を DB なしで検査する。"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Iterator, cast
from uuid import uuid4

import pytest
from test_sync_apply_port_change import (
    ChangeProjection,
    ChangeRights,
    ChangeSink,
    ChangeValidator,
)

from pitchlog.db.game_state.models import Game
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.tokens import ImmutableValue, TenantOperationResult
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync import change_path, invalidation, ports
from pitchlog.sync.idempotency import D5Candidate, StoredResult
from pitchlog.sync.model import AcceptedChangeResult, SyncEvent, SyncRequest
from pitchlog.sync.ports import PortRegistrationError
from pitchlog.sync.tokens import (
    InvalidationIntentDeliveredToken,
    InvalidationIntentPendingToken,
    InvalidationIntentReadToken,
)


def test_p3_target_requires_same_game_and_positive_slot() -> None:
    """V10 の他試合と不正 D4・D1 は保存前に拒否する。"""
    game_id = uuid4()
    event = SyncEvent(
        str(uuid4()),
        str(game_id),
        v10={"game": str(game_id), "d4": "2", "d1": 3},
    )
    assert change_path._target(event) == (game_id, 2, 3)
    with pytest.raises(ValueError, match="V10"):
        change_path._target(
            SyncEvent(
                event.d5,
                event.game_id,
                v10={"game": str(uuid4()), "d4": 2, "d1": 3},
            )
        )
    with pytest.raises(ValueError, match="V10"):
        change_path._target(
            SyncEvent(
                event.d5,
                event.game_id,
                v10={"game": event.game_id, "d4": 0, "d1": 3},
            )
        )


def test_p3_replay_keeps_original_accepted_at() -> None:
    """保存済み結果は現在時刻を採り直さず I6 をそのまま返す。"""
    event = SyncEvent(str(uuid4()), str(uuid4()))
    saved = StoredResult(
        "accepted",
        "fingerprint",
        cast(
            dict[str, ImmutableValue],
            {
                "target_reference": {
                    "試合": event.game_id,
                    "対象の D4": 1,
                    "対象の D1": 2,
                },
                "expected_version": 3,
                "confirmed_content": {"note": "first"},
                "accepted_at": "2026-10-14T00:00:00+00:00",
            },
        ),
        None,
    )
    result = change_path._accepted_from_candidate(
        D5Candidate("stored_result", stored=saved), event.d5
    )
    assert isinstance(result, AcceptedChangeResult)
    assert result.accepted_at == "2026-10-14T00:00:00+00:00"
    conflict = change_path._accepted_from_candidate(D5Candidate("conflict"), event.d5)
    assert conflict is not None and conflict.boundary == "B13"


def test_p3_rejects_unregistered_ports_before_any_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """登録表が空なら P3 の権利・投影・内容ポートを一つも呼ばない。"""
    game_id = uuid4()
    event = SyncEvent(str(uuid4()), str(game_id))
    request = SyncRequest("P3", str(game_id), (event,), recovery_generation="current")
    columns = tuple(Game.__table__.c.keys())
    row = tuple("in_progress" if name == "status" else None for name in columns)
    scope = cast(
        _TenantTransaction,
        SimpleNamespace(run=lambda _token: TenantOperationResult((row,))),
    )
    monkeypatch.setattr(change_path, "_lock_game_generation", lambda *_: (1, 0))
    monkeypatch.setattr(ports, "PORT_IMPLEMENTATIONS", frozenset())
    rights, projection, validator = (
        ChangeRights(),
        ChangeProjection(),
        ChangeValidator(),
    )
    with pytest.raises(PortRegistrationError):
        change_path._apply_locked(scope, request, rights, projection, validator)
    assert rights.calls == []
    assert projection.events == []
    assert validator.calls == 0


def test_delivery_pages_past_b06_and_retries_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#114 の行を読み飛ばしても後続の同期行へ進み、未完了を次回再試行する。"""
    monkeypatch.setattr(
        ports,
        "PORT_IMPLEMENTATIONS",
        frozenset(
            {
                (ChangeSink.__module__, ChangeSink.__name__),
                (ChangeRights.__module__, ChangeRights.__name__),
            }
        ),
    )
    states = {
        "14:first:game": "pending",
        "14:second:game": "pending",
        "sync:one:game": "pending",
        "sync:two:chart": "pending",
    }
    columns = invalidation._INTENT_COLUMNS
    game_id = uuid4()
    selectors: dict[str, dict[str, ImmutableValue]] = {
        "sync:one:game": {"game_id": game_id},
        "sync:two:chart": {"chart_kind": "spray"},
    }

    def run(token: object) -> TenantOperationResult:
        if isinstance(token, InvalidationIntentPendingToken):
            page = sorted(
                key
                for key, state in states.items()
                if state == "pending" and key > token.after_intent_id
            )[: token.limit]
            rows = tuple(
                tuple(
                    key
                    if name == "intent_id"
                    else key.split(":")[-1]
                    if name == "scope_kind"
                    else selectors.get(key, {}).get(name)
                    for name in columns
                )
                for key in page
            )
            return TenantOperationResult(rows)
        if isinstance(token, InvalidationIntentReadToken):
            row = tuple(
                token.intent_id
                if name == "intent_id"
                else states[token.intent_id]
                if name == "delivery_status"
                else None
                for name in columns
            )
            return TenantOperationResult((row,))
        assert isinstance(token, InvalidationIntentDeliveredToken)
        if states[token.intent_id] == "pending":
            states[token.intent_id] = "delivered"
            return TenantOperationResult(((1,),))
        return TenantOperationResult(((0,),))

    @contextmanager
    def fake_scope(_context: TenantContext) -> Iterator[_TenantTransaction]:
        yield cast(_TenantTransaction, SimpleNamespace(run=run))

    monkeypatch.setattr(invalidation, "tenant_transaction_scope", fake_scope)
    tenant_id = uuid4()
    context = cast(TenantContext, SimpleNamespace(tenant_id=tenant_id))
    sink = ChangeSink(complete=False)
    rights = ChangeRights()
    assert invalidation.deliver_pending_sync_intents(
        context, sink, rights, page_size=2
    ) == invalidation.DeliveryProgress(2, 0)
    assert all(state == "pending" for state in states.values())
    sink.complete = True
    assert invalidation.deliver_pending_sync_intents(
        context, sink, rights, page_size=2
    ) == invalidation.DeliveryProgress(2, 2)
    assert states == {
        "14:first:game": "pending",
        "14:second:game": "pending",
        "sync:one:game": "delivered",
        "sync:two:chart": "delivered",
    }
    assert len(sink.effects) == 2
    # 配信先の冪等キーは (tenant_id, intent_id)。テナントと範囲を値で渡す。
    by_id = {intent.intent_id: intent for intent in sink.intents}
    assert by_id["sync:one:game"].game_id == game_id
    assert by_id["sync:one:game"].target_tenant_id is None
    assert by_id["sync:two:chart"].chart_kind == "spray"
    assert by_id["sync:two:chart"].game_id is None
    assert {
        (intent.tenant_id, intent.intent_id, intent.scope_kind)
        for intent in sink.intents
    } == {
        (tenant_id, "sync:one:game", "game"),
        (tenant_id, "sync:two:chart", "chart"),
    }
