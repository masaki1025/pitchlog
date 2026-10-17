"""D-4 O5 のサーバー側: 列挙 7 箇所の検出と ACK への写像を DB なしで検査する。

受入条件 A(検出): 7 箇所の不変条件違反の永続状態を偽スコープの読取結果として
与え、局所入口(``apply_p1_event``・``apply_p2_event`` — 共通の ``_apply_event``)
が例外を外へ出さずに B3 + A5「拒否」(理由 O5)を返すことを確かめる。7 箇所の
状態は実 DB の制約・読取の条件・値域で作れない(US-1 提示 6-6)。取消の境界
(受入条件 B)は ``tests/db/test_sync_apply_o5_boundary.py`` が実 DB で確かめる。
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Literal, cast
from uuid import UUID, uuid4

import pytest
from test_authz_tenant_context import make_tenant_context
from test_sync_apply_port_prefix import PrefixProjection, PrefixRights, PrefixValidator
from test_sync_apply_prefix_path import _AcceptedObservation, _register_ports

from pitchlog.db.sync_protocol.models import OperationEvent, TemporaryPlayerIdMapping
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.tokens import (
    ImmutableValue,
    TenantOperationResult,
    TenantOperationToken,
)
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync import apply, ordering, prefix_path
from pitchlog.sync.idempotency import D5Candidate, StoredResult
from pitchlog.sync.invariants import O5_CODES, O5Code, O5InvariantViolation
from pitchlog.sync.model import AckResult, SyncEvent, SyncEventBatch, SyncRequest
from pitchlog.sync.ordering import apply_p2_event
from pitchlog.sync.ports import (
    ContentValidationPort,
    ProjectionPort,
    RecordingRightsPort,
)
from pitchlog.sync.prefix_path import P1Result, apply_p1_event
from pitchlog.sync.routing import route_for_event
from pitchlog.sync.tokens import (
    EventSlotReadToken,
    GameLockToken,
    OperationEventOrderReadToken,
    OperationEventReadToken,
    RecordingPrefixUpdateToken,
    TemporaryPlayerMappingReadToken,
)

GAME = "123e4567-e89b-12d3-a456-426614174000"
_EVENT_COLUMNS = tuple(OperationEvent.__table__.c.keys())
_MAPPING_COLUMNS = tuple(TemporaryPlayerIdMapping.__table__.c.keys())

# 7 箇所の固定文言(SP 6-3 の O5 の理由 = "O5: " + 文言)
_MESSAGES: dict[O5Code, str] = {
    "player_mapping_type": "正式選手 ID の型が不正",
    "d1_multiple_current_rows": "D1 に複数の現行行がある",
    "event_without_slot": "現行イベントのスロットがない",
    "d3_advance_failed": "D3 の前進に失敗",
    "d2_row_type": "D2 順の行の型が不正",
    "d2_out_of_range": "永続化済み D2 が bigint の値域外",
    "d2_no_gap": "D2 の局所再採番に必要な隙間がない",
}


class _BrokenStateScope(_AcceptedObservation):
    """未使用 D5・D3=0 の取引で、指定した不変条件違反の読取結果だけを返す。"""

    def __init__(self, code: O5Code | None) -> None:
        """壊す永続状態を一つ選ぶ。"""
        super().__init__()
        self.code = code

    def run(self, token: TenantOperationToken) -> TenantOperationResult:
        """壊した読取結果を返し、それ以外は受理まで進む観測へ委ねる。"""
        if isinstance(token, TemporaryPlayerMappingReadToken):
            self.tokens.append(type(token))
            if self.code != "player_mapping_type":
                return TenantOperationResult(())
            # 正式選手 ID の列は NOT NULL の Uuid なので、実 DB には作れない。
            row = tuple(
                "not-a-uuid" if column == "player_id" else None
                for column in _MAPPING_COLUMNS
            )
            return TenantOperationResult((row,))
        if isinstance(token, EventSlotReadToken):
            self.tokens.append(type(token))
            if self.code == "d1_multiple_current_rows":
                return TenantOperationResult(((1,), (2,)))
            return TenantOperationResult(())
        if isinstance(token, OperationEventReadToken):
            self.tokens.append(type(token))
            if self.code == "event_without_slot":
                return TenantOperationResult(((1,),))
            return TenantOperationResult(())
        if isinstance(token, RecordingPrefixUpdateToken):
            self.tokens.append(type(token))
            if self.code == "d3_advance_failed":
                return TenantOperationResult(((0,),))
            return TenantOperationResult(((1,),))
        if isinstance(token, OperationEventOrderReadToken):
            self.tokens.append(type(token))
            return TenantOperationResult(
                self._order_rows() if token.after_d2 == -1 else ()
            )
        return super().run(token)

    def _order_rows(self) -> tuple[tuple[ImmutableValue, ...], ...]:
        """P2 の D2 順の読取結果を、壊す状態に応じて作る。"""
        values: list[object]
        if self.code == "d2_row_type":
            values = ["10"]
        elif self.code == "d2_out_of_range":
            values = [-1]
        elif self.code == "d2_no_gap":
            values = [0, 1, 2, 3]
        else:
            values = []
        return tuple(
            tuple(
                cast(
                    ImmutableValue,
                    uuid4() if column == "id" else value if column == "d2" else None,
                )
                for column in _EVENT_COLUMNS
            )
            for value in values
        )


def _install(monkeypatch: pytest.MonkeyPatch, scope: _BrokenStateScope) -> None:
    """局所入口の取引だけを偽スコープへ替える(試合の認可読取も同じ偽スコープ)。"""
    _register_ports(monkeypatch)

    @contextmanager
    def fake_scope(_context: object) -> Iterator[_TenantTransaction]:
        """製品の局所入口に観測用のスコープを渡す。"""
        yield cast(_TenantTransaction, scope)

    monkeypatch.setattr(prefix_path, "tenant_transaction_scope", fake_scope)


def _p1_event(code: O5Code | None) -> SyncEvent:
    """選手参照を一つ持つ P1 の毎球入力(D1=1)を作る。"""
    payload = {"player_id": str(uuid4())} if code == "player_mapping_type" else {}
    return SyncEvent(
        str(uuid4()), GAME, 1, "epoch", v5="play_input", v6=10, v7=payload, v8={}
    )


def _apply(
    monkeypatch: pytest.MonkeyPatch, code: O5Code | None, path: Literal["P1", "P2"]
) -> tuple[P1Result, _BrokenStateScope]:
    """壊した永続状態を与え、実際の局所入口から一件進める。"""
    scope = _BrokenStateScope(code)
    _install(monkeypatch, scope)
    context = make_tenant_context(UUID(GAME))
    event = _p1_event(code)
    if path == "P2":
        monkeypatch.setattr(ordering, "_MAX_D2", 3)
        event = SyncEvent(
            event.d5, GAME, 1, "epoch", v5="play_input", v6=2, v7={}, v8={}
        )
        result = apply_p2_event(
            context, event, PrefixRights(), PrefixProjection(), PrefixValidator(), None
        )
    else:
        result = apply_p1_event(
            context, event, PrefixRights(), PrefixProjection(), PrefixValidator(), None
        )
    return result, scope


_SITES: tuple[tuple[O5Code, Literal["P1", "P2"]], ...] = (
    ("player_mapping_type", "P1"),
    ("d1_multiple_current_rows", "P1"),
    ("event_without_slot", "P1"),
    ("d3_advance_failed", "P1"),
    ("d2_row_type", "P2"),
    ("d2_out_of_range", "P2"),
    ("d2_no_gap", "P2"),
)


def test_sites_cover_every_enumerated_code() -> None:
    """受入条件 A の対象が列挙 7 件の全部である。"""
    assert {code for code, _ in _SITES} == O5_CODES == set(_MESSAGES)


@pytest.mark.parametrize(("code", "path"), _SITES, ids=[code for code, _ in _SITES])
def test_each_enumerated_site_returns_o5_without_raising(
    monkeypatch: pytest.MonkeyPatch, code: O5Code, path: Literal["P1", "P2"]
) -> None:
    """受入条件 A: 各箇所の永続状態で B3 + A5「拒否」(O5)を返し、例外を出さない。"""
    result, _scope = _apply(monkeypatch, code, path)
    assert result == P1Result(
        "B3",
        0,
        False,
        a5="拒否",
        reason=f"O5: {_MESSAGES[code]}",
        b3_code="O5",
    )


@pytest.mark.parametrize(
    ("port", "method"),
    [
        (PrefixRights, "holds_recording_right"),
        (PrefixValidator, "validate"),
        (PrefixProjection, "apply"),
    ],
)
def test_port_raised_o5_type_stays_b7(
    monkeypatch: pytest.MonkeyPatch, port: type, method: str
) -> None:
    """ポートが O5 の型を送出しても O5 にせず、B7 の例外として上げる(design 12-2)。"""

    def raise_o5(*_args: object) -> None:
        raise O5InvariantViolation("d2_no_gap", "ポートからの送出")

    monkeypatch.setattr(port, method, raise_o5)
    with pytest.raises(RuntimeError, match="ポートが O5 の型を送出した") as raised:
        _apply(monkeypatch, None, "P1")
    assert type(raised.value) is RuntimeError
    assert isinstance(raised.value.__cause__, O5InvariantViolation)


def test_o5_type_has_no_subclasses() -> None:
    """部分型で列挙の突合を迂回させない(送出の突合は型名で数える)。"""
    assert O5InvariantViolation.__subclasses__() == []


@pytest.mark.parametrize("path", ["P1", "P2"])
def test_intact_state_is_accepted(
    monkeypatch: pytest.MonkeyPatch, path: Literal["P1", "P2"]
) -> None:
    """壊さない状態では同じ偽スコープで受理になる(偽スコープ自体の対照)。"""
    result, _scope = _apply(monkeypatch, None, path)
    assert result.accepted and result.b3_code is None


def test_unenumerated_runtime_error_is_not_o5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """負例: 列挙の外の不変条件(認可後の試合行消失)は例外のまま B7 へ上がる。"""

    class VanishedGame(_BrokenStateScope):
        """認可の読取の後、試合行のロックで行が消えている。"""

        def run(self, token: TenantOperationToken) -> TenantOperationResult:
            """試合行のロックだけ空を返す。"""
            if isinstance(token, GameLockToken):
                return TenantOperationResult(())
            return super().run(token)

    _install(monkeypatch, VanishedGame(None))
    with pytest.raises(RuntimeError, match="認可後に試合行が消失した") as raised:
        apply_p1_event(
            make_tenant_context(UUID(GAME)),
            _p1_event(None),
            PrefixRights(),
            PrefixProjection(),
            PrefixValidator(),
            None,
        )
    assert type(raised.value) is RuntimeError


@pytest.mark.parametrize(
    ("result", "message"),
    [
        ({"state": "受理", "d3": -1, "temporary_id_mapping": {}}, "結果の形が不正"),
        (
            {"state": "受理", "d3": 1, "temporary_id_mapping": {"t": 1}},
            "写像の形が不正",
        ),
    ],
)
def test_corrupted_saved_result_replay_is_not_o5(
    monkeypatch: pytest.MonkeyPatch, result: dict[str, object], message: str
) -> None:
    """負例: 保存済み結果の再掲で見つけた破損は O5 にせず B7 のまま(11-1)。"""
    _install(monkeypatch, _BrokenStateScope(None))
    stored = D5Candidate(
        "stored_result",
        stored=StoredResult(
            "accepted", "fingerprint", cast(Mapping[str, ImmutableValue], result), None
        ),
    )
    monkeypatch.setattr(prefix_path, "classify_d5", lambda *_args: stored)
    with pytest.raises(RuntimeError, match=message) as raised:
        apply_p1_event(
            make_tenant_context(UUID(GAME)),
            _p1_event(None),
            PrefixRights(),
            PrefixProjection(),
            PrefixValidator(),
            None,
        )
    assert type(raised.value) is RuntimeError


def _ports() -> tuple[RecordingRightsPort, ProjectionPort, ContentValidationPort]:
    """下位経路を差し替える試験用の不透明なポートを返す。"""
    return (
        cast(RecordingRightsPort, object()),
        cast(ProjectionPort, object()),
        cast(ContentValidationPort, object()),
    )


_O5_RESULT = P1Result(
    "B3", 0, False, a5="拒否", reason="O5: D3 の前進に失敗", b3_code="O5"
)
_O4_RESULT = P1Result(
    "B3", 2, False, a5="拒否", reason="O4: 永続化済み D2 の同値", b3_code="O4"
)


@pytest.mark.parametrize("entry", ["request", "events"])
@pytest.mark.parametrize(
    ("stop", "branch"), [(_O5_RESULT, "O5"), (_O4_RESULT, "O4")], ids=["O5", "O4"]
)
def test_b3_code_decides_ack_branch_and_stops_later_events(
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
    stop: P1Result,
    branch: str,
) -> None:
    """O5・O4 の B3 を区分で ACK へ写し、前方は受理・後続は未処理にする。"""
    game = str(uuid4())
    events = tuple(
        SyncEvent(str(uuid4()), game, d1, "1", v5="game_end_declaration", v6=10, v7={})
        for d1 in (1, 2, 3, 4)
    )
    monkeypatch.setattr(apply, "game_accessible", lambda *_: True)

    def preflight(*args: object) -> apply._BatchPreflight:
        batch = args[4] if len(args) > 4 else None
        return apply._BatchPreflight(
            0,
            tuple(D5Candidate("unused") for _ in events),
            True,
            1,
            paths=(
                None
                if batch is None
                else {cast(int, event.d1): route_for_event(event) for event in events}
            ),
        )

    def run(*args: object, **_kwargs: object) -> P1Result:
        event = cast(SyncEvent, args[2])
        if event.d1 == 3:
            return stop
        return P1Result(None, cast(int, event.d1), True)

    monkeypatch.setattr(apply, "_preflight_d1", preflight)
    monkeypatch.setattr(apply, "_run_d1_event", run)
    context = cast(TenantContext, object())
    if entry == "request":
        result = apply.apply_sync_request(
            context, SyncRequest("P1", game, events, d4="1", v12="proof"), *_ports()
        )
    else:
        result = apply.apply_sync_events(
            context, SyncEventBatch(game, "1", events, v12="proof"), *_ports()
        )
    assert isinstance(result, AckResult)
    assert (result.boundary, result.b3_branch, result.d3) == ("B3", branch, 2)
    assert result.reason == stop.reason
    assert [(row.d1, row.state, row.reason) for row in result.a5] == [
        (1, "受理", None),
        (2, "受理", None),
        (3, "拒否", stop.reason),
        (4, "未処理", None),
    ]
