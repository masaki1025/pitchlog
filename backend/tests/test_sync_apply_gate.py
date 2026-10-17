"""RG1 の閉鎖と再検証が各局所経路で D5 より先に働くことを確かめる。"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, cast
from uuid import uuid4

import pytest
from test_sync_apply_port_change import ChangeRights, ChangeSink, ChangeValidator
from test_sync_apply_port_prefix import (
    PrefixProjection,
    PrefixRights,
    PrefixValidator,
)

from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync import (
    change_path,
    invalidation,
    ordering,
    ports,
    prefix_path,
    rejection,
)
from pitchlog.sync.model import (
    AcceptedChangeResult,
    ChangeResult,
    RejectedChangeResult,
    SyncEvent,
    SyncRequest,
)
from pitchlog.sync.ports import PortWriter
from pitchlog.sync.prefix_path import P1Result
from pitchlog.sync.rejection import RejectionResult
from pitchlog.sync.tokens import (
    GameLockToken,
    GameReadToken,
    IdempotencyLedgerInsertToken,
)


class _Scope:
    """発行された token と取引の確定・取消を記録する。"""

    def __init__(self, *, game_present: bool = True) -> None:
        """空の観測列を用意する。"""
        self.tokens: list[type[TenantOperationToken]] = []
        self.rolled_back = False
        self.game_present = game_present

    def run(self, token: TenantOperationToken) -> TenantOperationResult:
        """試合行が見つからない結果を返す。"""
        self.tokens.append(type(token))
        if isinstance(token, GameReadToken) and self.game_present:
            return TenantOperationResult(((token.game_id,),))
        return TenantOperationResult(())


def _invoke(
    path: str, rights: PrefixRights | ChangeRights, game_id: str, d5: str
) -> P1Result | RejectionResult | ChangeResult:
    """対象経路の公開入口だけを呼ぶ。"""
    context = cast(TenantContext, object())
    if path == "P3":
        event = SyncEvent(d5, game_id, v5="play_change", v7={})
        request = SyncRequest("P3", game_id, (event,), recovery_generation="current")
        return change_path.apply_p3_change(
            context,
            request,
            cast(ChangeRights, rights),
            PrefixProjection(),
            ChangeValidator(),
        )
    event = SyncEvent(d5, game_id, 1, "1", v5="game_end_declaration", v6=10, v7={})
    if path == "P1":
        return prefix_path.apply_p1_event(
            context,
            event,
            cast(PrefixRights, rights),
            PrefixProjection(),
            PrefixValidator(),
            "proof",
        )
    if path == "P2":
        return ordering.apply_p2_event(
            context,
            event,
            cast(PrefixRights, rights),
            PrefixProjection(),
            PrefixValidator(),
            "proof",
        )
    return rejection.apply_rejection_or_escrow(
        context,
        event,
        cast(PrefixRights, rights),
        "proof",
        path="P4" if path == "P4" else "P1",
        reason="内容拒否",
    )


@pytest.mark.parametrize("path", ["P1", "P2", "P3", "P4", "P5"])
@pytest.mark.parametrize("failure", ["closed", "error"])
def test_rg1_before_d5_stops_without_lock_or_d5(
    monkeypatch: pytest.MonkeyPatch, path: str, failure: str
) -> None:
    """③の非ロック認可後、③-a の閉鎖・例外は行ロック前に止まる。"""
    scope = _Scope()

    @contextmanager
    def fake_scope(_context: TenantContext) -> Iterator[_TenantTransaction]:
        try:
            yield cast(_TenantTransaction, scope)
        except Exception:
            scope.rolled_back = True
            raise

    module = (
        change_path
        if path == "P3"
        else rejection
        if path in ("P4", "P5")
        else prefix_path
    )
    monkeypatch.setattr(module, "tenant_transaction_scope", fake_scope)
    monkeypatch.setattr(
        ports,
        "PORT_IMPLEMENTATIONS",
        frozenset(
            (cls.__module__, cls.__name__) for cls in (PrefixRights, ChangeRights)
        ),
    )
    rights: PrefixRights | ChangeRights = (
        ChangeRights(
            restoration=failure == "closed",
            fail_at="read" if failure == "error" else None,
        )
        if path == "P3"
        else PrefixRights(
            read_open=failure != "closed",
            fail_at="read" if failure == "error" else None,
        )
    )
    result = _invoke(path, rights, str(uuid4()), str(uuid4()))
    assert result.boundary == ("B10" if path == "P3" else "B7")
    assert scope.rolled_back
    assert scope.tokens == [GameReadToken]
    assert rights.writer is not None
    with pytest.raises(RuntimeError, match="閉じている"):
        rights.writer.run(GameLockToken(uuid4()))


def test_port_writer_is_issued_before_first_lock_and_closed_at_scope_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """試合行を読む前に同一書き手が発行され、⑧まで有効に保たれる。"""
    scope = _Scope()

    @contextmanager
    def fake_scope(_context: TenantContext) -> Iterator[_TenantTransaction]:
        yield cast(_TenantTransaction, scope)

    monkeypatch.setattr(prefix_path, "tenant_transaction_scope", fake_scope)
    monkeypatch.setattr(
        ports,
        "PORT_IMPLEMENTATIONS",
        frozenset({(PrefixRights.__module__, PrefixRights.__name__)}),
    )
    rights = PrefixRights()
    original_read = rights.read_rg1_before_d5

    def observe_read(writer: PortWriter) -> bool:
        assert scope.tokens == [GameReadToken]
        return original_read(writer)

    monkeypatch.setattr(rights, "read_rg1_before_d5", observe_read)

    def no_write(*_args: object, **_kwargs: object) -> P1Result:
        scope.run(GameLockToken(uuid4()))
        return P1Result("B2", 0, False)

    monkeypatch.setattr(prefix_path, "_apply_locked", no_write)
    result = _invoke("P1", rights, str(uuid4()), str(uuid4()))
    assert result.boundary == "B2"
    assert rights.rg1_calls == ["read"]
    assert scope.tokens == [GameReadToken, GameLockToken]
    assert rights.writer is not None
    with pytest.raises(RuntimeError, match="閉じている"):
        rights.writer.run(GameLockToken(uuid4()))


def test_lost_game_after_authorization_is_not_returned_as_b12(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """③通過後に試合行が失われても、RG1 後の B12 へ戻さない。"""
    scope = _Scope()

    @contextmanager
    def fake_scope(_context: TenantContext) -> Iterator[_TenantTransaction]:
        yield cast(_TenantTransaction, scope)

    monkeypatch.setattr(change_path, "tenant_transaction_scope", fake_scope)
    monkeypatch.setattr(
        ports,
        "PORT_IMPLEMENTATIONS",
        frozenset({(ChangeRights.__module__, ChangeRights.__name__)}),
    )
    rights = ChangeRights()
    with pytest.raises(RuntimeError, match="認可後に試合行が消失"):
        _invoke("P3", rights, str(uuid4()), str(uuid4()))
    assert rights.calls == ["rg1_read"]
    assert scope.tokens == [GameReadToken, GameLockToken]


@pytest.mark.parametrize("path", ["P1", "P2", "P3", "P4", "P5"])
def test_inaccessible_game_stops_before_rg1_even_when_closed(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """B6/B12 は復元状態にも対象試合の実在にも依存しない。"""
    scope = _Scope(game_present=False)

    @contextmanager
    def fake_scope(_context: TenantContext) -> Iterator[_TenantTransaction]:
        yield cast(_TenantTransaction, scope)

    module = (
        change_path
        if path == "P3"
        else rejection
        if path in ("P4", "P5")
        else prefix_path
    )
    monkeypatch.setattr(module, "tenant_transaction_scope", fake_scope)
    rights: PrefixRights | ChangeRights = (
        ChangeRights(restoration=True)
        if path == "P3"
        else PrefixRights(read_open=False)
    )
    result = _invoke(path, rights, str(uuid4()), str(uuid4()))
    assert result.boundary == ("B12" if path == "P3" else "B6")
    assert scope.tokens == [GameReadToken]
    assert rights.writer is None
    if isinstance(rights, ChangeRights):
        assert rights.calls == []
    else:
        assert rights.rg1_calls == []


@pytest.mark.parametrize("failure", ["closed", "error"])
def test_internal_delivery_is_deferred_before_pending_query(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """内部配信は③-a が閉じると一覧を読まず、配信先も呼ばない。"""
    scope = _Scope()

    @contextmanager
    def fake_scope(_context: TenantContext) -> Iterator[_TenantTransaction]:
        try:
            yield cast(_TenantTransaction, scope)
        except Exception:
            scope.rolled_back = True
            raise

    monkeypatch.setattr(invalidation, "tenant_transaction_scope", fake_scope)
    monkeypatch.setattr(
        ports,
        "PORT_IMPLEMENTATIONS",
        frozenset((cls.__module__, cls.__name__) for cls in (ChangeRights, ChangeSink)),
    )
    rights = ChangeRights(
        restoration=failure == "closed",
        fail_at="read" if failure == "error" else None,
    )
    sink = ChangeSink()
    progress = invalidation.deliver_pending_sync_intents(
        cast(TenantContext, object()), sink, rights
    )
    assert progress == invalidation.DeliveryProgress(0, 0)
    assert scope.rolled_back
    assert scope.tokens == []
    assert sink.calls == []
    assert rights.calls == ["rg1_read"]


@pytest.mark.parametrize("path", ["P1", "P2", "P3", "P4", "P5"])
def test_no_write_branch_does_not_take_commit_rg1_lock(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """保存を伴わない境界結果に⑧の FOR SHARE を要求しない。"""
    scope = _Scope()

    @contextmanager
    def fake_scope(_context: TenantContext) -> Iterator[_TenantTransaction]:
        yield cast(_TenantTransaction, scope)

    module = (
        change_path
        if path == "P3"
        else rejection
        if path in ("P4", "P5")
        else prefix_path
    )
    monkeypatch.setattr(module, "tenant_transaction_scope", fake_scope)
    monkeypatch.setattr(
        ports,
        "PORT_IMPLEMENTATIONS",
        frozenset(
            (cls.__module__, cls.__name__) for cls in (PrefixRights, ChangeRights)
        ),
    )
    d5 = str(uuid4())

    def no_write(
        *_args: object, **_kwargs: object
    ) -> ChangeResult | P1Result | RejectionResult:
        if path == "P3":
            return RejectedChangeResult("B9", d5, b9_cause="記録権不保持")
        if path in ("P4", "P5"):
            return RejectionResult("B3b", 0, "拒否")
        return P1Result("B2", 0, False)

    monkeypatch.setattr(module, "_apply_locked", no_write)
    rights: PrefixRights | ChangeRights = (
        ChangeRights() if path == "P3" else PrefixRights()
    )
    _invoke(path, rights, str(uuid4()), d5)
    assert scope.tokens == [GameReadToken]
    if isinstance(rights, ChangeRights):
        assert rights.calls == ["rg1_read"]
    else:
        assert rights.rg1_calls == ["read"]


@pytest.mark.parametrize("path", ["P1", "P2", "P3", "P4", "P5"])
@pytest.mark.parametrize("failure", ["closed", "error"])
def test_rg1_before_commit_rolls_back_without_consuming_d5(
    monkeypatch: pytest.MonkeyPatch, path: str, failure: str
) -> None:
    """⑧ の閉鎖・例外では経路の局所結果より B7/B10 を優先する。"""
    scope = _Scope()

    @contextmanager
    def fake_scope(_context: TenantContext) -> Iterator[_TenantTransaction]:
        try:
            yield cast(_TenantTransaction, scope)
        except Exception:
            scope.rolled_back = True
            raise

    module = (
        change_path
        if path == "P3"
        else rejection
        if path in ("P4", "P5")
        else prefix_path
    )
    monkeypatch.setattr(module, "tenant_transaction_scope", fake_scope)
    monkeypatch.setattr(
        ports,
        "PORT_IMPLEMENTATIONS",
        frozenset(
            (cls.__module__, cls.__name__) for cls in (PrefixRights, ChangeRights)
        ),
    )
    d5 = str(uuid4())

    def accepted(
        *_args: object, **_kwargs: object
    ) -> ChangeResult | P1Result | RejectionResult:
        scope.tokens.append(IdempotencyLedgerInsertToken)
        if path == "P3":
            return AcceptedChangeResult(
                {"試合": str(uuid4()), "対象の D4": 1, "対象の D1": 1},
                1,
                d5,
                {},
                "now",
            )
        if path in ("P4", "P5"):
            return RejectionResult(
                "B4" if path == "P4" else "B3a",
                0,
                "退避" if path == "P4" else "拒否",
            )
        return P1Result(None, 1, True)

    monkeypatch.setattr(module, "_apply_locked", accepted)
    rights: PrefixRights | ChangeRights = (
        ChangeRights(
            restoration_after_first=failure == "closed",
            fail_at="commit" if failure == "error" else None,
        )
        if path == "P3"
        else PrefixRights(
            commit_open=failure != "closed",
            fail_at="commit" if failure == "error" else None,
        )
    )
    result = _invoke(path, rights, str(uuid4()), d5)
    assert result.boundary == ("B10" if path == "P3" else "B7")
    assert scope.rolled_back
    assert scope.tokens == [GameReadToken, IdempotencyLedgerInsertToken]
    assert rights.writer is not None
    with pytest.raises(RuntimeError, match="閉じている"):
        rights.writer.run(GameLockToken(uuid4()))
