"""V5の⑦局所解決と、P2の既順序/原値/保存tokenをDBなしで検査する。

合成Portとscopeは試験だけへ登録する。実権利/認可/DB保存の成功を表さない。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from types import MappingProxyType
from typing import cast
from uuid import UUID

import pytest
from test_authz_tenant_context import make_tenant_context
from test_sync_apply_ordering import _P2AcceptedObservation
from test_sync_apply_port_prefix import (
    DenyPrefixRights,
    PrefixProjection,
    PrefixRights,
    PrefixValidator,
)
from test_sync_apply_prefix_path import D5, GAME, _LockObservation, _register_ports

from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync import prefix_path
from pitchlog.sync.idempotency import (
    D5Candidate,
    StoredResult,
    event_source,
    event_source_fingerprint,
    operation_fingerprint,
)
from pitchlog.sync.model import ABSENT, StageValue, SyncEvent
from pitchlog.sync.ordering import _assign_d2, apply_p2_event
from pitchlog.sync.prefix_path import (
    P1ContentRejection,
    P1PreconditionError,
    _apply_locked,
    _event_kind,
)
from pitchlog.sync.tokens import (
    IdempotencyLedgerInsertToken,
    OperationEventOrderReadToken,
)


class _PersistedTokenObservation(_P2AcceptedObservation):
    """既合成scopeへ台帳tokenの全値観測だけを加える。"""

    def __init__(self, positions: list[int] | None = None) -> None:
        """初期空D2またはO4用の既順序を使う。"""
        super().__init__([] if positions is None else positions)
        self.ledgers: list[IdempotencyLedgerInsertToken] = []

    def run_in_savepoint(self, token: TenantOperationToken) -> TenantOperationResult:
        """製品の台帳組立値を捕捉し、既試験scopeへ委譲する。"""
        if type(token) is IdempotencyLedgerInsertToken:
            self.ledgers.append(token)
        return super().run_in_savepoint(token)


def _event(
    v5: StageValue = "1", *, d1: int = 1, v6: StageValue = 10, v8: StageValue = None
) -> SyncEvent:
    """原wireを保持する毎球イベントを構成する。"""
    return SyncEvent(
        D5,
        GAME,
        d1,
        "epoch",
        v5=v5,
        v6=v6,
        v7={"resultId": "batting-result.ball"},
        v8={"stateFields": {"state.count.balls": {"before": "0", "after": "1"}}}
        if v8 is None
        else v8,
    )


def _public_p2(
    monkeypatch: pytest.MonkeyPatch,
    event: SyncEvent,
    scope: _PersistedTokenObservation,
    rights: PrefixRights,
    projection: PrefixProjection,
):
    """公開P2入口を既合成Port/同scopeだけで実行する。"""
    _register_ports(monkeypatch)

    @contextmanager
    def fake_scope(_context: object) -> Iterator[_TenantTransaction]:
        yield cast(_TenantTransaction, scope)

    monkeypatch.setattr(prefix_path, "tenant_transaction_scope", fake_scope)
    return apply_p2_event(
        make_tenant_context(UUID(GAME)),
        event,
        rights,
        projection,
        PrefixValidator(),
        "proof",
    )


@pytest.mark.parametrize(
    "kind",
    [
        "play_input",
        "undo",
        "substitution",
        "tiebreak_start",
        "game_end_declaration",
        "player_registration",
    ],
)
def test_existing_internal_literals_are_unchanged(kind: str) -> None:
    """旧内部DBliteralは別名変換を通さず同じ値のまま返す。"""
    assert _event_kind(_event(kind)) == kind


@pytest.mark.parametrize(
    "v5", [None, True, 1, "", "01", " 1", "2", "unknown", "state_correction"]
)
def test_old_v5_rejection_reason_is_unchanged(v5: StageValue) -> None:
    """対象外値の旧V5拒否文言を保持する。"""
    with pytest.raises(P1PreconditionError) as error:
        _event_kind(_event(v5))
    assert str(error.value) == "P1 の V5 は D1 付きイベント種別が必要"


@pytest.mark.parametrize("v5", [None, True, 1, "", "01", "2", "unknown", "undo"])
def test_p2_rejects_nonlogical_input_with_the_original_reason(
    monkeypatch: pytest.MonkeyPatch,
    v5: StageValue,
) -> None:
    """⑦でP2参加条件を先に判定する旧枝/拒否理由を保持する。"""
    _register_ports(monkeypatch)
    scope = _PersistedTokenObservation()
    with pytest.raises(P1ContentRejection) as error:
        _apply_locked(
            cast(_TenantTransaction, scope),
            _event(v5),
            PrefixRights(),
            PrefixProjection(),
            PrefixValidator(),
            "proof",
            None,
            None,
            path="P2",
            order_resolver=_assign_d2,
        )
    assert str(error.value) == "P2 は論理位置を持つイベント種別だけを受ける"
    assert scope.ledgers == scope.events == []


def test_wire_one_resolves_only_the_database_column_and_preserves_raw_fingerprints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """公開P2の保存tokenはplay_input、原event/投影/台帳指紋はwire1を保持する。"""
    event, scope = _event(), _PersistedTokenObservation()
    source_before = event_source(event)
    event_fp = event_source_fingerprint(event)
    operation_fp = operation_fingerprint(event, "P2", None)
    projection, rights = PrefixProjection(), PrefixRights()
    result = _public_p2(monkeypatch, event, scope, rights, projection)
    assert result.accepted and not result.replayed and result.d3 == 1
    assert len(scope.events) == len(scope.ledgers) == len(projection.events) == 1
    saved = scope.events[0]
    assert saved.event_kind == "play_input" and saved.d2 == 10
    assert json.loads(saved.payload_json) == {"resultId": "batting-result.ball"}
    assert json.loads(saved.state_diff_json or "null") == event.v8
    assert projection.events[0].v5 == event.v5 == "1"
    assert projection.events[0].v7 == event.v7 and projection.events[0].v8 == event.v8
    assert scope.ledgers[0].source_fingerprint == operation_fp
    assert event_source(event) == source_before
    assert event_source_fingerprint(event) == event_fp
    assert operation_fingerprint(event, "P2", None) == operation_fp
    assert rights.rg1_calls == ["read", "commit"]


@pytest.mark.parametrize("field", ["v6", "v8"])
def test_wire_one_keeps_required_d2_and_state_difference(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    """V5解決を理由にV6/V8の既必須条件を省略しない。"""
    _register_ports(monkeypatch)
    scope = _PersistedTokenObservation()
    event = _event(v6=ABSENT) if field == "v6" else _event(v8=ABSENT)
    with pytest.raises(P1ContentRejection) as error:
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
    assert str(error.value) == (
        "このイベント種別には D2 が必要"
        if field == "v6"
        else "このイベント種別には V8 の状態差分が必要"
    )
    assert scope.ledgers == scope.events == []


@pytest.mark.parametrize("candidate_kind", ["stored_result", "conflict"])
def test_existing_d5_result_is_returned_before_codec_or_ports(
    monkeypatch: pytest.MonkeyPatch,
    candidate_kind: str,
) -> None:
    """再掲/異内容B3bのどちらも⑦codecと合成Port登録より先に終わる。"""
    event = _event()
    fingerprint = operation_fingerprint(event, "P2", None)
    saved = StoredResult(
        "accepted",
        fingerprint,
        MappingProxyType(
            {"state": "受理", "d3": 1, "temporary_id_mapping": MappingProxyType({})}
        ),
        None,
    )
    candidate = (
        D5Candidate("stored_result", stored=saved)
        if candidate_kind == "stored_result"
        else D5Candidate("conflict", boundary="B3b")
    )

    def classify(_scope, _d5, actual_fingerprint, path):
        assert actual_fingerprint == fingerprint and path == "P2"
        return candidate

    def forbidden_codec(_value: object) -> str:
        raise AssertionError("再掲/異内容ではcodecへ進まない")

    monkeypatch.setattr(prefix_path, "classify_d5", classify)
    monkeypatch.setattr(prefix_path, "first_ball_database_kind", forbidden_codec)
    result = _apply_locked(
        cast(_TenantTransaction, _LockObservation()),
        event,
        PrefixRights(),
        PrefixProjection(),
        PrefixValidator(),
        "proof",
        None,
        None,
        path="P2",
    )
    assert result.accepted is (candidate_kind == "stored_result")
    assert (result.replayed, result.boundary) == (
        (True, None) if candidate_kind == "stored_result" else (False, "B3b")
    )
    assert event.v5 == "1"


@pytest.mark.parametrize("stop", ["rights", "sequence", "rg1"])
def test_prior_rejections_never_reach_codec(
    monkeypatch: pytest.MonkeyPatch,
    stop: str,
) -> None:
    """RG1/⑤権利/⑥連番の先行拒否で⑦codecを実行しない。"""

    def forbidden_codec(_value: object) -> str:
        raise AssertionError("先行拒否ではcodecへ進まない")

    monkeypatch.setattr(prefix_path, "first_ball_database_kind", forbidden_codec)
    scope, projection = _PersistedTokenObservation(), PrefixProjection()
    rights = (
        DenyPrefixRights()
        if stop == "rights"
        else PrefixRights(read_open=stop != "rg1")
    )
    event = _event(d1=3 if stop == "sequence" else 1)
    if stop == "rights":
        with pytest.raises(P1PreconditionError) as error:
            _public_p2(monkeypatch, event, scope, rights, projection)
        assert error.value.category == "recording_rights"
    else:
        result = _public_p2(monkeypatch, event, scope, rights, projection)
        assert result.boundary == ("B2" if stop == "sequence" else "B7")
    assert scope.ledgers == scope.events == projection.events == []


def test_p2_o4_is_not_bypassed_for_wire_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """既存D2同値のO4をV5解決で成功にしない。"""
    scope, projection = _PersistedTokenObservation([10, 10]), PrefixProjection()
    event = _event()
    result = _public_p2(monkeypatch, event, scope, PrefixRights(), projection)
    assert not result.accepted and result.boundary == "B3"
    assert result.reason == "O4: 永続化済み D2 の同値"
    assert scope.ledgers == scope.events == projection.events == []


def test_codec_fault_propagates_before_writes_and_closes_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """故障を成功へ補完せず原値を保持し、同じwriterを失効させる。"""
    fault = RuntimeError("codec unavailable")

    def unavailable(_value: object) -> str:
        raise fault

    monkeypatch.setattr(prefix_path, "first_ball_database_kind", unavailable)
    event, scope, rights = _event(), _PersistedTokenObservation(), PrefixRights()
    fingerprint = operation_fingerprint(event, "P2", None)
    with pytest.raises(RuntimeError) as error:
        _public_p2(monkeypatch, event, scope, rights, PrefixProjection())
    assert error.value is fault
    assert scope.ledgers == scope.events == []
    assert event.v5 == "1" and operation_fingerprint(event, "P2", None) == fingerprint
    assert rights.writer is not None
    with pytest.raises(RuntimeError, match="閉じている"):
        rights.writer.run(OperationEventOrderReadToken(UUID(GAME), -1, 2))
