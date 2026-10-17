"""D-4 O5 の取消の境界(受入条件 B)を使い捨て製品 DB で確かめる。

O5 の全取消は検出の箇所に依らない性質なので、既存の名前付き注入点
(``sync/crash_points.py`` の ``reach`` と、試験だけが設置する
``testing_crash_hook``)から、取引の中の書き込みの後で**列挙済みの**
``O5InvariantViolation`` を送出して確かめる(US-1 提示 6-6)。製品コードに新しい
注入の口は足さない。検出の箇所ごとの検査は ``tests/test_sync_apply_o5.py``
(受入条件 A)が行う。

合成の投影ポートは DB に書かないため、投影の取消は「対象の投影結果が残らない」
ことを DB では観測できない。ポートの書き手を含む取消は、同じ取引の他の書き込み
(台帳・イベント・スロット・D3・再採番・写像・無効化意図)が残らないことで確かめる。
"""

from __future__ import annotations

from typing import Literal, LiteralString
from uuid import UUID, uuid4

import pytest
from test_authz_tenant_context import make_tenant_context
from test_sync_apply_port_prefix import (
    DenyPrefixRights,
    PrefixProjection,
    PrefixRights,
    PrefixValidator,
)

from pitchlog.sync import ports
from pitchlog.sync.apply import apply_sync_events, apply_sync_request
from pitchlog.sync.crash_points import CrashPoint
from pitchlog.sync.crash_points import testing_crash_hook as _testing_crash_hook
from pitchlog.sync.invariants import O5_CODES, O5Code, O5InvariantViolation
from pitchlog.sync.model import AckResult, SyncEvent, SyncEventBatch, SyncRequest
from pitchlog.sync.prefix_path import PlayerRegistration

from .test_sync_apply_operations_boundary import _SyncDatabase, sync_database
from .test_sync_apply_prefix_path_boundary import _event, prefix_database

__all__ = ("sync_database", "prefix_database")

pytestmark = pytest.mark.requires_db

type _Entry = Literal["request", "events"]
type _Kind = Literal["P1", "P2", "P1-registration"]

_TARGET_D1 = 3


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
            )
        ),
    )


def _scalar(
    db: _SyncDatabase, sql: LiteralString, params: tuple[object, ...]
) -> object:
    """独立した接続で一つの値を読む。"""
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
    db.catalog.applicator.rollback()
    assert row is not None
    return row[0]


_COUNT_D5: dict[str, LiteralString] = {
    "idempotency_ledger": (
        "SELECT count(*) FROM idempotency_ledger WHERE tenant_id = %s AND d5 = %s"
    ),
    "operation_events": (
        "SELECT count(*) FROM operation_events WHERE tenant_id = %s AND d5 = %s"
    ),
    "rejected_event_originals": (
        "SELECT count(*) FROM rejected_event_originals WHERE tenant_id = %s AND d5 = %s"
    ),
}


def _count_d5(db: _SyncDatabase, table: str, d5: str) -> object:
    """許可した同期表の対象 D5 の行数を読む。"""
    return _scalar(db, _COUNT_D5[table], (db.tenant_a, UUID(d5)))


def _home_team(db: _SyncDatabase) -> UUID:
    """その場登録の選手を置くチームを読む。"""
    team = _scalar(
        db,
        "SELECT home_team_record_id FROM games WHERE tenant_id = %s AND id = %s",
        (db.tenant_a, db.game_a),
    )
    assert isinstance(team, UUID)
    return team


def _events(
    db: _SyncDatabase, entry: _Entry, kind: _Kind, temporary: UUID
) -> tuple[SyncEvent, SyncEvent, SyncEvent, SyncEvent]:
    """前方 2 件・対象(D1=3)・後続 1 件を作る。

    P2 の対象は前方の D2(9・10)と重なる V6=10 を持ち、局所再採番(10 → 11)を
    起こしてから停止する。その場登録の対象は一時 ID を参照する。混在バッチでは
    前方・後続を P2 の種別(毎球入力)にし、対象の経路だけを変える。
    """

    def play(d1: int, d2: int) -> SyncEvent:
        """P2 へ振り分けられる毎球入力を作る。"""
        return SyncEvent(
            str(uuid4()), str(db.game_a), d1, "1", v5="play_input", v6=d2, v7={}, v8={}
        )

    if kind == "P2" or entry == "events":
        first, second, later = play(1, 9), play(2, 10), play(4, 40)
    else:
        first = _event(db.game_a, d1=1, d4="1")
        second = _event(db.game_a, d1=2, d4="1")
        later = _event(db.game_a, d1=4, d4="1")
    if kind == "P2":
        target = play(_TARGET_D1, 10)
    elif kind == "P1-registration":
        target = _event(
            db.game_a,
            d1=_TARGET_D1,
            d4="1",
            kind="player_registration",
            payload={"player_id": str(temporary)},
        )
    else:
        target = _event(db.game_a, d1=_TARGET_D1, d4="1")
    return first, second, target, later


def _apply(
    db: _SyncDatabase,
    entry: _Entry,
    kind: _Kind,
    events: tuple[SyncEvent, ...],
    registration: PlayerRegistration,
) -> AckResult:
    """公開入口(要求単一経路または混在バッチ)へ渡す。"""
    registrations = {_TARGET_D1: registration} if kind == "P1-registration" else None
    context = make_tenant_context(db.tenant_a)
    ordered = tuple(reversed(events))
    if entry == "request":
        result = apply_sync_request(
            context,
            SyncRequest(
                "P2" if kind == "P2" else "P1",
                str(db.game_a),
                ordered,
                d4="1",
                v12="proof",
            ),
            PrefixRights(),
            PrefixProjection(),
            PrefixValidator(),
            registrations=registrations,
        )
    else:
        result = apply_sync_events(
            context,
            SyncEventBatch(str(db.game_a), "1", ordered, v12="proof"),
            PrefixRights(),
            PrefixProjection(),
            PrefixValidator(),
            registrations=registrations,
        )
    assert isinstance(result, AckResult)
    return result


# (入口, 経路, 送出する注入点, 送出する列挙済みの code)。注入点は取引の中の
# 書き込みの後だけ: T1(台帳)・T3(D3)・T4(投影)・D1 の無効化意図・
# T5(再採番)・T6(一時 ID の写像)。
_CASES: tuple[tuple[_Entry, _Kind, CrashPoint, O5Code], ...] = (
    ("request", "P1", "after_t1_ledger", "player_mapping_type"),
    ("request", "P1", "after_t3_prefix", "d3_advance_failed"),
    ("request", "P1", "after_t4_projection", "event_without_slot"),
    ("request", "P1", "after_d1_intents", "d1_multiple_current_rows"),
    ("request", "P2", "after_t5_order", "d2_no_gap"),
    ("request", "P2", "after_t4_projection", "d2_row_type"),
    ("request", "P1-registration", "after_t6_mapping", "player_mapping_type"),
    ("events", "P2", "after_t5_order", "d2_out_of_range"),
    ("events", "P1-registration", "after_t3_prefix", "d3_advance_failed"),
    ("events", "P1-registration", "after_t6_mapping", "event_without_slot"),
)


def test_cases_use_only_enumerated_codes() -> None:
    """注入する例外は列挙済みの code だけを使う。"""
    assert {code for *_, code in _CASES} <= O5_CODES


@pytest.mark.parametrize(
    ("entry", "kind", "point", "code"),
    _CASES,
    ids=[f"{entry}-{kind}-{point}" for entry, kind, point, _ in _CASES],
)
def test_o5_rolls_back_target_event_and_keeps_prefix_in_same_ack(
    prefix_database: _SyncDatabase,
    entry: _Entry,
    kind: _Kind,
    point: CrashPoint,
    code: O5Code,
) -> None:
    """受入条件 B: 対象の取引を全取消し、D5 を消費せず、前方は同じ ACK で確定。"""
    db = prefix_database
    temporary = uuid4()
    registration = PlayerRegistration(temporary, _home_team(db), "O5 登録", "active")
    events = _events(db, entry, kind, temporary)
    first, second, target, later = events
    message = "注入した不変条件違反"
    reached: list[CrashPoint] = []
    started = 0

    def inject(name: CrashPoint) -> None:
        """対象イベント(3 件目の取引)の指定点でだけ O5 を送出する。"""
        nonlocal started
        if name == "before_transaction":
            started += 1
        if started == _TARGET_D1:
            reached.append(name)
            if name == point:
                raise O5InvariantViolation(code, message)

    with _testing_crash_hook(inject):
        result = _apply(db, entry, kind, events, registration)

    assert point in reached
    reason = f"O5: {message}"
    assert (result.boundary, result.b3_branch, result.d3, result.reason) == (
        "B3",
        "O5",
        2,
        reason,
    )
    assert [(row.d1, row.state, row.reason) for row in result.a5] == [
        (1, "受理", None),
        (2, "受理", None),
        (3, "拒否", reason),
        (4, "未処理", None),
    ]
    assert dict(result.temporary_id_mapping) == {}
    # 前方は確定、対象は D5 を消費せず T9 も作らない、後続は未処理。
    for event, expected in ((first, 1), (second, 1), (target, 0), (later, 0)):
        assert _count_d5(db, "idempotency_ledger", event.d5) == expected
        assert _count_d5(db, "operation_events", event.d5) == expected
        assert _count_d5(db, "rejected_event_originals", event.d5) == 0
    assert (
        _scalar(
            db,
            "SELECT confirmed_watermark FROM recording_generations "
            "WHERE tenant_id = %s AND game_id = %s AND generation = 1",
            (db.tenant_a, db.game_a),
        )
        == 2
    )
    assert (
        _scalar(
            db,
            "SELECT count(*) FROM event_slots WHERE tenant_id = %s AND game_id = %s "
            "AND d1 >= %s",
            (db.tenant_a, db.game_a, _TARGET_D1),
        )
        == 0
    )
    assert (
        _scalar(
            db,
            "SELECT count(*) FROM invalidation_intents "
            "WHERE tenant_id = %s AND intent_id LIKE %s",
            (db.tenant_a, f"sync:{target.d5}:%"),
        )
        == 0
    )
    assert (
        _scalar(
            db,
            "SELECT count(*) FROM invalidation_intents "
            "WHERE tenant_id = %s AND intent_id LIKE %s",
            (db.tenant_a, f"sync:{first.d5}:%"),
        )
        == 5
    )
    assert (
        _scalar(
            db,
            "SELECT count(*) FROM temporary_player_id_mappings "
            "WHERE tenant_id = %s AND temporary_id = %s",
            (db.tenant_a, temporary),
        )
        == 0
    )
    assert (
        _scalar(
            db,
            "SELECT count(*) FROM players WHERE tenant_id = %s AND name = %s",
            (db.tenant_a, "O5 登録"),
        )
        == 0
    )
    if kind == "P2":
        # 局所再採番(前方 D1=2 の D2 10 → 11)も取り消されている。
        with db.catalog.applicator.cursor() as cursor:
            cursor.execute(
                "SELECT d1, d2 FROM operation_events WHERE tenant_id = %s "
                "AND game_id = %s ORDER BY d1",
                (db.tenant_a, db.game_a),
            )
            assert cursor.fetchall() == [(1, 9), (2, 10)]
        db.catalog.applicator.rollback()

    # 是正の後(hook を外す)に内容も D5 も変えずに再送すると受理される。
    resent = _apply(db, entry, kind, events, registration)
    assert (resent.boundary, resent.b3_branch, resent.d3) == ("B1", None, 4)
    assert [(row.d1, row.state) for row in resent.a5] == [
        (1, "重複"),
        (2, "重複"),
        (3, "受理"),
        (4, "受理"),
    ]
    for event in events:
        assert _count_d5(db, "idempotency_ledger", event.d5) == 1
        assert _count_d5(db, "operation_events", event.d5) == 1


@pytest.mark.parametrize("entry", ["request", "events"])
def test_unenumerated_runtime_error_from_hook_is_not_o5(
    prefix_database: _SyncDatabase, entry: _Entry
) -> None:
    """負例: 列挙の外の RuntimeError は O5 にならず、例外のまま(500 → B7)。"""
    db = prefix_database
    temporary = uuid4()
    registration = PlayerRegistration(temporary, _home_team(db), "O5 負例", "active")
    kind: _Kind = "P1" if entry == "request" else "P1-registration"
    events = _events(db, entry, kind, temporary)
    started = 0

    def inject(name: CrashPoint) -> None:
        """対象イベントの D3 前進の後で列挙の外の例外を送出する。"""
        nonlocal started
        if name == "before_transaction":
            started += 1
        if started == _TARGET_D1 and name == "after_t3_prefix":
            raise RuntimeError("列挙の外の不変条件違反")

    with _testing_crash_hook(inject):
        with pytest.raises(RuntimeError, match="列挙の外") as raised:
            _apply(db, entry, kind, events, registration)
    assert not isinstance(raised.value, O5InvariantViolation)
    assert _count_d5(db, "idempotency_ledger", events[2].d5) == 0
    assert _count_d5(db, "operation_events", events[2].d5) == 0
