"""P2 の局所再採番・同値停止と共通ロック順を DB なしで検査する。"""

from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import pytest
from test_sync_apply_port_prefix import PrefixProjection, PrefixRights, PrefixValidator
from test_sync_apply_prefix_path import (
    _AcceptedObservation,
    _LockObservation,
    _register_ports,
)

from pitchlog.db.sync_protocol.models import OperationEvent
from pitchlog.repositories.base import _operation_spec
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync import ordering, prefix_path
from pitchlog.sync.idempotency import D5Candidate
from pitchlog.sync.model import ABSENT, SyncEvent
from pitchlog.sync.ordering import _assign_d2
from pitchlog.sync.prefix_path import P1PreconditionError, _apply_locked
from pitchlog.sync.tokens import (
    GameLockToken,
    IdempotencyLedgerReadToken,
    OperationEventOrderReadToken,
    OperationEventOrderUpdateToken,
    RecordingGenerationLockToken,
    RecordingGenerationReadToken,
)

GAME = UUID("123e4567-e89b-12d3-a456-426614174000")
_EVENT_COLUMNS = tuple(OperationEvent.__table__.c.keys())


class _OrderScope:
    """正本列順の行をページングし、UPDATE の順を記録する。"""

    def __init__(self, positions: list[int]) -> None:
        """試験ごとに独立な順序行を作る。"""
        self.entries = [(uuid4(), position) for position in positions]
        self.updated: list[tuple[UUID, int]] = []

    def run(self, token: TenantOperationToken) -> TenantOperationResult:
        """同じ D2 のときは ID 順で返す。"""
        if isinstance(token, OperationEventOrderReadToken):
            rows = sorted(
                (
                    (identifier, d2)
                    for identifier, d2 in self.entries
                    if d2 > token.after_d2
                ),
                key=lambda item: (item[1], item[0]),
            )[: token.limit]
            return TenantOperationResult(
                tuple(
                    tuple(
                        identifier if column == "id" else d2 if column == "d2" else None
                        for column in _EVENT_COLUMNS
                    )
                    for identifier, d2 in rows
                )
            )
        if isinstance(token, OperationEventOrderUpdateToken):
            self.updated.append((token.id, token.d2))
            self.entries = [
                (identifier, token.d2 if identifier == token.id else d2)
                for identifier, d2 in self.entries
            ]
            return TenantOperationResult(())
        raise AssertionError(f"想定しない token: {type(token).__name__}")


class _P2AcceptedObservation(_AcceptedObservation):
    """P2 の T5 読み取りを P1 の確定 token 観測へ加える。"""

    def __init__(self, positions: list[int]) -> None:
        """採番前の有効な D2 を指定する。"""
        super().__init__()
        self.order = _OrderScope(positions)

    def run(self, token: TenantOperationToken) -> TenantOperationResult:
        """T5 だけ順序行の偽スコープへ委譲する。"""
        if isinstance(
            token, (OperationEventOrderReadToken, OperationEventOrderUpdateToken)
        ):
            return self.order.run(token)
        return super().run(token)


def test_p2_shifts_only_dense_suffix_from_v6() -> None:
    """O2: 左に空きがない 10・11 を右の空きへ逆順に移す。"""
    scope = _OrderScope([9, 10, 11, 20])
    assert _assign_d2(cast(_TenantTransaction, scope), GAME, 10) == 10
    assert [d2 for _, d2 in scope.updated] == [12, 11]
    assert sorted(d2 for _, d2 in scope.entries) == [9, 11, 12, 20]


def test_p2_uses_left_gap_without_renumbering() -> None:
    """指定位置 20 の直前が空いていれば、既存の 20 を動かさない。"""
    scope = _OrderScope([10, 20])
    assert _assign_d2(cast(_TenantTransaction, scope), GAME, 20) == 19
    assert scope.updated == []


def test_p2_persists_assigned_gap_in_event_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T5 の採番値を保存 token と投影ポートの双方へ渡す。"""
    _register_ports(monkeypatch)
    scope = _P2AcceptedObservation([10, 20])
    event = SyncEvent(
        str(uuid4()), str(GAME), 1, "epoch", v5="play_input", v6=20, v7={}, v8={}
    )
    projection = PrefixProjection()
    result = _apply_locked(
        cast(_TenantTransaction, scope),
        event,
        PrefixRights(),
        projection,
        PrefixValidator(),
        "proof",
        None,
        None,
        path="P2",
        order_resolver=_assign_d2,
    )
    assert result.accepted
    assert len(scope.events) == 1 and scope.events[0].d2 == 19
    assert len(projection.events) == 1 and projection.events[0].v6 == 19
    assert event.v6 == 20


def test_p2_uses_exact_v6_when_unoccupied() -> None:
    """指定値そのものが空いていれば、その D2 を採番する。"""
    scope = _OrderScope([10, 20])
    assert _assign_d2(cast(_TenantTransaction, scope), GAME, 15) == 15
    assert scope.updated == []


def test_p2_shifts_left_at_bigint_limit() -> None:
    """右へ動かせない最大値でも、左の局所的な空きを使える。"""
    maximum = ordering._MAX_D2
    scope = _OrderScope([maximum - 1, maximum])
    left_id, right_id = (identifier for identifier, _ in scope.entries)
    assert _assign_d2(cast(_TenantTransaction, scope), GAME, maximum) == maximum - 1
    assert scope.updated == [(left_id, maximum - 2)]
    assert dict(scope.entries) == {left_id: maximum - 2, right_id: maximum}


def test_p2_saves_without_collision_at_bigint_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """最大値で左へ動かした行と、新イベントの保存 D2 が衝突しない。"""
    _register_ports(monkeypatch)
    maximum = ordering._MAX_D2
    scope = _P2AcceptedObservation([maximum - 1, maximum])
    left_id, right_id = (identifier for identifier, _ in scope.order.entries)
    event = SyncEvent(
        str(uuid4()),
        str(GAME),
        1,
        "epoch",
        v5="play_input",
        v6=maximum,
        v7={},
        v8={},
    )
    projection = PrefixProjection()
    result = _apply_locked(
        cast(_TenantTransaction, scope),
        event,
        PrefixRights(),
        projection,
        PrefixValidator(),
        "proof",
        None,
        None,
        path="P2",
        order_resolver=_assign_d2,
    )
    assert result.accepted
    assert scope.order.updated == [(left_id, maximum - 2)]
    assert dict(scope.order.entries) == {left_id: maximum - 2, right_id: maximum}
    assert len(scope.events) == 1 and scope.events[0].d2 == maximum - 1
    assert len(projection.events) == 1 and projection.events[0].v6 == maximum - 1
    assigned_positions = {d2 for _, d2 in scope.order.entries}
    assigned_positions.add(scope.events[0].d2)
    assert assigned_positions == {maximum - 2, maximum - 1, maximum}


def test_p2_rejects_when_both_sides_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """両側の値域がすべて埋まった場合だけ採番を拒否する。"""
    monkeypatch.setattr(ordering, "_MAX_D2", 3)
    scope = _OrderScope([0, 1, 2, 3])
    with pytest.raises(P1PreconditionError, match="隙間がない"):
        _assign_d2(cast(_TenantTransaction, scope), GAME, 2)
    assert scope.updated == []


def test_p2_rejects_v6_above_bigint_limit() -> None:
    """上限を超える V6 は書き込み前に拒否する。"""
    scope = _OrderScope([])
    with pytest.raises(P1PreconditionError, match="bigint"):
        _assign_d2(cast(_TenantTransaction, scope), GAME, ordering._MAX_D2 + 1)
    assert scope.updated == []


def test_p2_finds_persisted_equal_d2_before_any_update() -> None:
    """O4: 別位置にある永続同値でも、再採番へ進まない。"""
    scope = _OrderScope([2, 10, 11, 30, 30])
    assert _assign_d2(cast(_TenantTransaction, scope), GAME, 10) is None
    assert scope.updated == []


def test_p2_detects_equal_d2_across_page_boundary() -> None:
    """D2 キーセットの境界を跨ぐ同値も O4 にする。"""
    scope = _OrderScope([*range(256), 255])
    assert _assign_d2(cast(_TenantTransaction, scope), GAME, 0) is None
    assert scope.updated == []


def test_p2_locks_game_before_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    """R-16: P2 でも試合行の FOR UPDATE が世代行より先。"""
    _register_ports(monkeypatch)
    scope = _LockObservation()
    event = SyncEvent(
        str(uuid4()), str(GAME), 3, "epoch", v5="play_input", v6=10, v7={}, v8={}
    )
    result = _apply_locked(
        cast(_TenantTransaction, scope),
        event,
        PrefixRights(),
        PrefixProjection(),
        PrefixValidator(),
        "proof",
        None,
        None,
        path="P2",
        order_resolver=_assign_d2,
    )
    assert result.boundary == "B2"
    assert scope.tokens[:3] == [
        GameLockToken,
        RecordingGenerationReadToken,
        RecordingGenerationLockToken,
    ]
    assert _operation_spec(GameLockToken(GAME)).for_update
    assert not _operation_spec(RecordingGenerationReadToken(GAME)).for_update
    assert _operation_spec(RecordingGenerationLockToken(GAME, 1)).for_update


def test_p2_classifies_reused_d5_before_invalid_v5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """異なる V5 の再送も先に D5 の B3b 候補へ分類する。"""
    scope = _LockObservation()
    event = SyncEvent(
        str(uuid4()), str(GAME), 1, "epoch", v5="player_registration", v7={}
    )
    observed: list[str] = []

    def conflict(
        _scope: _TenantTransaction, _d5: UUID, _fingerprint: str, path: str
    ) -> D5Candidate:
        """D5 台帳が同じキーに別内容を保持した状態を作る。"""
        observed.append(path)
        return D5Candidate("conflict", boundary="B3b")

    monkeypatch.setattr(prefix_path, "classify_d5", conflict)
    result = _apply_locked(
        cast(_TenantTransaction, scope),
        event,
        PrefixRights(),
        PrefixProjection(),
        PrefixValidator(),
        "proof",
        None,
        None,
        path="P2",
        order_resolver=_assign_d2,
    )
    assert result.boundary == "B3b"
    assert observed == ["P2"]
    assert scope.tokens == [
        GameLockToken,
        RecordingGenerationReadToken,
        RecordingGenerationLockToken,
    ]


@pytest.mark.parametrize(
    ("v6", "v8", "v10", "v11", "message"),
    [
        (ABSENT, {}, ABSENT, ABSENT, "D2"),
        (10, ABSENT, ABSENT, ABSENT, "V8"),
        (10, {}, {"game": str(GAME), "d4": "epoch", "d1": 1}, ABSENT, "V10"),
        (10, {}, ABSENT, 7, "V11"),
    ],
)
def test_p2_inherits_c12_checks_before_write(
    monkeypatch: pytest.MonkeyPatch,
    v6: object,
    v8: object,
    v10: object,
    v11: object,
    message: str,
) -> None:
    """P2 も P1 の共通経路で種別表の V 条件を保存前に検査する。"""
    _register_ports(monkeypatch)
    scope = _LockObservation()
    event = SyncEvent(
        str(uuid4()),
        str(GAME),
        1,
        "epoch",
        v5="play_input",
        v6=v6,
        v7={},
        v8=v8,
        v10=v10,
        v11=v11,
    )
    with pytest.raises(P1PreconditionError, match=message):
        _apply_locked(
            cast(_TenantTransaction, scope),
            event,
            PrefixRights(),
            PrefixProjection(),
            PrefixValidator(),
            "proof",
            None,
            None,
            path="P2",
            order_resolver=_assign_d2,
        )
    assert scope.tokens == [
        GameLockToken,
        RecordingGenerationReadToken,
        RecordingGenerationLockToken,
        IdempotencyLedgerReadToken,
    ]
