"""NFR-019(d) のサーバー側 runner — 資産を読み、公開入口へ注入して DB を観測する。

期待値は資産だけが持ち、この runner は持たない(正本 10-3)。runner は資産の入力から
要求を組み立て、case の注入対象・注入時点で故障を起こし、観測点ごとの実際の状態を
DB と応答から読み、結果検査 ``validate_failure_scenario_result`` へ渡す。

T 要素の証拠(独立に証明できないものを含む — worklog に記録):
- T1・T6 の結果 = 対象 D5 の台帳行(T1 と T6 は同じ行を証拠にする)
- T2 = スロット行・イベント行 / T3 = 確定水位が対象 D1 以上
- T4 = 投影ポートが対象を受け取り、かつ同じトランザクションが確定した(T1 の行)。
  投影の永続化は U-X1 の持ち物で、U-S1 の DB に跡が残らないため
- T5 = イベント行の D2 / T6 の写像 = 一時 ID 写像行
- T7 = 対象スロットの確定版と、P3 の意図 ID の行 / T8・T9 = 台帳行と原本行
無い証拠は、その送信で故障を注入して中断したなら ``notCommitted``、そうでなければ
``no-write``(書かないことが正しい)とする。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, LiteralString, cast
from uuid import UUID

import pytest
from test_authz_tenant_context import make_tenant_context
from test_sync_apply_failure_contract import (
    OWNED_SCENARIO_IDS,
    T_ELEMENT_UNITS,
    ApplicationPath,
    FailureScenarioContractError,
    load_transaction_routes,
    validate_failure_scenario_contract,
    validate_failure_scenario_result,
)
from test_sync_apply_port_change import (
    ChangeProjection,
    ChangeRights,
    ChangeSink,
    ChangeValidator,
    ConsumedThenCrashSink,
    InjectedDeliveryCrash,
)
from test_sync_apply_port_prefix import (
    DenyPrefixRights,
    PrefixProjection,
    PrefixRights,
    PrefixValidator,
    RejectPrefixValidator,
)

from pitchlog.sync import ports
from pitchlog.sync.apply import apply_sync_request
from pitchlog.sync.crash_points import CrashPoint
from pitchlog.sync.crash_points import testing_crash_hook as _testing_crash_hook
from pitchlog.sync.invalidation import deliver_pending_sync_intents
from pitchlog.sync.model import (
    ABSENT,
    AcceptedChangeResult,
    AckResult,
    RejectedChangeResult,
    SyncEvent,
    SyncRequest,
)
from pitchlog.sync.prefix_path import PlayerRegistration

from .test_sync_apply_operations_boundary import _SyncDatabase, sync_database
from .test_sync_apply_prefix_path_boundary import prefix_database

__all__ = ("sync_database", "prefix_database")

pytestmark = pytest.mark.requires_db

_FIXTURE_DIRECTORY = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "sync-protocol-failures"
)
_ROUTES = load_transaction_routes()
_REGISTERED_NAME = "注入選手"

# クライアント runner(ステップ 20)が観測する case とフィールド。サーバー runner は
# 残りを観測する。両者の和が case の全実値フィールドになることを下の試験で照合する。
CLIENT_OBSERVED_FIELDS: Mapping[tuple[str, str], frozenset[str]] = {
    ("p3-crash-boundaries", "server-confirmed-before-i6"): frozenset(
        (
            "i6TargetReference",
            "i6Version",
            "i6D5",
            "i6ConfirmedContent",
            "i6RetentionDeadline",
            "i6EscrowState",
        )
    ),
}

# 資産の注入時点の語彙 → 名前付きの注入点(crash_points)。
_CRASH_POINTS: dict[str, CrashPoint] = {
    "T1 の保存後・コミット前": "after_t1_ledger",
    "T2 の保存後・コミット前": "after_t2_event",
    "T3 の保存後・コミット前": "after_t3_prefix",
    "T4 の保存後・コミット前": "after_t4_projection",
    "T5 の保存後・コミット前": "after_t5_order",
    "T6 の保存後・コミット前": "after_t6_result",
    "T6 の写像の保存後・コミット前": "after_t6_mapping",
    "T7 の保存後・コミット前": "after_t7_intents",
    "T8 の台帳の保存後": "after_t8_ledger",
    "T8 の原本の保存後": "after_t8_original",
    "T8 の確定後・B4 応答の前": "after_transaction",
    "T9 の台帳の保存後": "after_t9_ledger",
    "T9 の原本の保存後": "after_t9_original",
}
_D1_KINDS_WITH_D2 = frozenset(
    ("play_input", "substitution", "tiebreak_start", "game_end_declaration")
)


class _InjectedCrash(RuntimeError):
    """資産の注入点で起こす電源断。"""


@pytest.fixture(autouse=True)
def _register_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runner の合成ポートだけを登録し、製品の登録表を空のままにする。"""
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
                ChangeSink,
                ConsumedThenCrashSink,
            )
        ),
    )


def _assets() -> list[tuple[str, dict[str, Any]]]:
    assets = []
    for path in sorted(_FIXTURE_DIRECTORY.glob("*.json")):
        asset = json.loads(path.read_text(encoding="utf-8"))
        validate_failure_scenario_contract(path.name, asset, _ROUTES)
        assets.append((path.name, asset))
    return assets


def _server_path(asset: Mapping[str, Any]) -> str | None:
    field_value = asset["input"]["applicationPath"]
    return field_value.get("value")


_SERVER_ASSETS = [asset for _, asset in _assets() if _server_path(asset) is not None]
_SERVER_CASE_PAIRS = [
    (asset, case) for asset in _SERVER_ASSETS for case in asset["cases"]
]
_SERVER_CASES = [
    pytest.param(asset, case, id=f"{asset['scenarioId']}:{case['caseId']}")
    for asset, case in _SERVER_CASE_PAIRS
]


@dataclass
class _Run:
    """1 case の実行状態。"""

    db: _SyncDatabase
    asset: Mapping[str, Any]
    case: Mapping[str, Any]
    namespace: UUID = field(default_factory=uuid.uuid4)
    projected: set[str] = field(default_factory=set)
    sink: ChangeSink = field(default_factory=ChangeSink)
    interrupted: bool = False
    response: object | None = None
    previous_mapping: Mapping[str, str] | None = None
    rights_verdict: bool | None = None
    recovery_verdict: bool | None = None
    last_request: SyncRequest | None = None
    handed_over: bool = False

    @property
    def path(self) -> ApplicationPath:
        return self.asset["input"]["applicationPath"]["value"]

    @property
    def queue(self) -> Mapping[str, Any]:
        return self.asset["input"]["queue"]["value"]

    def uuid(self, name: str) -> UUID:
        """資産の名前から、この実行に固有の UUID を決定的に作る。"""
        return uuid.uuid5(self.namespace, name)

    @property
    def game(self) -> UUID:
        return self.db.game_a

    def subject(self) -> Mapping[str, Any]:
        name = self.queue["subject"]
        events = [*self.queue["unsent"], *self.queue.get("restartUnsent", [])]
        return next(event for event in events if event["d5"] == name)


def _sql(
    db: _SyncDatabase, statement: LiteralString, params: Sequence[object]
) -> list[tuple]:
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(statement, tuple(params))
        rows = cursor.fetchall() if cursor.description else []
    db.catalog.applicator.rollback()
    return rows


def _execute(
    db: _SyncDatabase, statement: LiteralString, params: Sequence[object]
) -> None:
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(statement, tuple(params))
    db.catalog.applicator.commit()


def _event(run: _Run, spec: Mapping[str, Any]) -> SyncEvent:
    """資産のイベント記述から D1 付きイベントを作る。"""
    kind = spec["kind"]
    payload = json.loads(json.dumps(spec["payload"]))
    if "registration" in spec:
        payload = {
            key: str(run.uuid(value)) if value == spec["registration"] else value
            for key, value in payload.items()
        }
    replacement = spec.get("tombstoneOf") or spec.get("revisionOf")
    v9: object = ABSENT
    v10: object = ABSENT
    if replacement is not None:
        flag = "tombstone" if "tombstoneOf" in spec else "revision"
        v9 = {flag: True, "rejected_d5": str(run.uuid(replacement))}
        v10 = {"game": str(run.game), "d4": "1", "d1": spec["d1"]}
    tombstone = "tombstoneOf" in spec
    return SyncEvent(
        str(run.uuid(spec["d5"])),
        str(run.game),
        spec["d1"],
        "1",
        v5=kind,
        v6=(
            spec.get("d2", spec["d1"] * 10)
            if not tombstone and kind in _D1_KINDS_WITH_D2
            else ABSENT
        ),
        v7=payload,
        v8=(
            {}
            if not tombstone and kind in {"play_input", "state_correction"}
            else ABSENT
        ),
        v9=v9,
        v10=v10,
    )


def _change_event(run: _Run, spec: Mapping[str, Any]) -> SyncEvent:
    """資産の P3 記述から D1 なし変更イベントを作る。"""
    return SyncEvent(
        str(run.uuid(spec["d5"])),
        str(run.game),
        v5=spec["kind"],
        v7=spec["payload"],
        v10={"game": str(run.game), "d4": 1, "d1": spec["target"]["d1"]},
        v11=spec["expectedVersion"],
    )


def _registrations(
    run: _Run, events: Sequence[Mapping[str, Any]]
) -> dict[str, PlayerRegistration]:
    registered = [event for event in events if "registration" in event]
    if not registered:
        return {}
    team = _sql(
        run.db,
        "SELECT home_team_record_id FROM games WHERE tenant_id = %s AND id = %s",
        (run.db.tenant_a, run.game),
    )[0][0]
    return {
        str(run.uuid(event["d5"])): PlayerRegistration(
            run.uuid(event["registration"]), team, _REGISTERED_NAME, "active"
        )
        for event in registered
    }


def _send(
    run: _Run,
    events: Sequence[Mapping[str, Any]],
    *,
    rights: PrefixRights | ChangeRights | None = None,
    reject: bool | None = None,
    hook: Callable[[CrashPoint], None] | None = None,
    seed: bool = False,
) -> object:
    """資産の経路で公開入口へ 1 要求を送り、応答を返す。

    初期永続状態の投入(``seed``)は、P3 の資産でも D1 付きイベントとして送る。
    """
    if run.path == "P3" and not seed:
        request = SyncRequest(
            "P3",
            str(run.game),
            tuple(_change_event(run, spec) for spec in events),
            recovery_generation="current",
            v12="proof",
        )
        selected_rights: PrefixRights | ChangeRights = rights or ChangeRights()
        projection: PrefixProjection | ChangeProjection = ChangeProjection()
        validator: PrefixValidator | ChangeValidator = ChangeValidator()
    else:
        request = SyncRequest(
            "P2" if run.path == "P2" else "P1",
            str(run.game),
            tuple(_event(run, spec) for spec in events),
            d4="1",
            v12="proof",
        )
        selected_rights = rights or (
            DenyPrefixRights() if run.path == "P4" else PrefixRights()
        )
        projection = PrefixProjection()
        rejecting = run.path == "P5" if reject is None else reject
        validator = RejectPrefixValidator() if rejecting else PrefixValidator()
    run.last_request = request
    # ⑤ は未使用 D5 を含む要求だけで評価する。評価しなかった送信は null で表す。
    run.rights_verdict = None
    run.recovery_verdict = None
    try:
        with _testing_crash_hook(hook or (lambda _point: None)):
            response = apply_sync_request(
                make_tenant_context(run.db.tenant_a),
                request,
                selected_rights,
                projection,
                validator,
                registrations=_registrations(run, events),
            )
    finally:
        run.projected.update(event.d5 for event in projection.events)
        if isinstance(selected_rights, ChangeRights):
            if "holds" in selected_rights.calls:
                run.rights_verdict = selected_rights.holds
            if "recovery" in selected_rights.calls:
                run.recovery_verdict = selected_rights.current
        elif selected_rights.calls:
            run.rights_verdict = not isinstance(selected_rights, DenyPrefixRights)
    return response


@contextmanager
def _equal_d2(run: _Run, pair: Sequence[str]) -> Iterator[None]:
    """O4: 部分一意索引を外し、2 イベントの D2 を同値にした永続状態を作る。"""
    first, second = (run.uuid(name) for name in pair)
    original = _sql(
        run.db,
        "SELECT d2 FROM operation_events WHERE tenant_id = %s AND d5 = %s",
        (run.db.tenant_a, second),
    )[0][0]
    _execute(run.db, "DROP INDEX uq_operation_events_active_d2", ())
    _execute(
        run.db,
        "UPDATE operation_events SET d2 = (SELECT d2 FROM operation_events "
        "WHERE tenant_id = %s AND d5 = %s) WHERE tenant_id = %s AND d5 = %s",
        (run.db.tenant_a, first, run.db.tenant_a, second),
    )
    try:
        yield
    finally:
        _execute(
            run.db,
            "UPDATE operation_events SET d2 = %s WHERE tenant_id = %s AND d5 = %s",
            (original, run.db.tenant_a, second),
        )
        _execute(
            run.db,
            "CREATE UNIQUE INDEX uq_operation_events_active_d2 "
            "ON operation_events (tenant_id, game_id, d2) "
            "WHERE d2 IS NOT NULL AND replaced_at IS NULL AND retired_at IS NULL",
            (),
        )


def _seed(run: _Run, stack: list[Callable[[], Any]]) -> None:
    """資産の初期永続状態を、公開入口と使い捨て DB の操作で作る。"""
    initial = run.asset["input"]["initialPersistence"]["value"]
    for step in initial["seed"]:
        if "accept" in step:
            response = _send(
                run, step["accept"], rights=PrefixRights(), reject=False, seed=True
            )
            assert isinstance(response, AckResult) and response.boundary == "B1"
        elif "rejectContent" in step:
            response = _send(
                run,
                step["rejectContent"],
                rights=PrefixRights(),
                reject=True,
                seed=True,
            )
            assert isinstance(response, AckResult) and response.boundary == "B3"
        elif "equalD2" in step:
            context = _equal_d2(run, step["equalD2"])
            context.__enter__()
            stack.append(lambda: context.__exit__(None, None, None))
        elif "deliverPending" in step:
            # 初期状態の outbox を配信済みにし、観測対象の意図だけを未配信にする。
            deliver_pending_sync_intents(
                make_tenant_context(run.db.tenant_a), ChangeSink(), ChangeRights()
            )
        elif "gameStatus" in step:
            _execute(
                run.db,
                "UPDATE games SET status = %s WHERE tenant_id = %s AND id = %s",
                (step["gameStatus"], run.db.tenant_a, run.game),
            )
        else:
            raise AssertionError(f"未知の初期永続状態: {step}")
    for original in initial.get("originals", []):
        content = original["content"]
        seeded = [
            event
            for step in initial["seed"]
            for event in step.get("accept", [])
            if event["d5"] == original["d5"]
            and {"d1": event["d1"], "kind": event["kind"], "payload": event["payload"]}
            == content
        ]
        assert seeded, f"先着原本を初期永続状態として作れていない: {original}"
    run.response = None
    run.rights_verdict = None
    run.recovery_verdict = None


def _hand_over(run: _Run) -> None:
    """記録権の引き継ぎ: 世代 1 を失効・退役させ、D3 = 0 の世代 2 を作る。"""
    _execute(
        run.db,
        "UPDATE recording_generations SET revoked_at = now(), retired_at = now() "
        "WHERE tenant_id = %s AND game_id = %s AND generation = 1",
        (run.db.tenant_a, run.game),
    )
    _execute(
        run.db,
        "INSERT INTO recording_generations (tenant_id, game_id, generation, "
        "kind, issuance_order, holder_device) "
        "VALUES (%s, %s, 2, 'normal', 2, 'new-device')",
        (run.db.tenant_a, run.game),
    )
    run.handed_over = True


def _inject(run: _Run) -> int:
    """Case の注入を実行し、注入点の呼び出し回数を返す。"""
    injection = run.case["faultInjection"]
    target = injection["target"]["value"]
    point = injection["injectionPoint"]["value"]
    unsent = run.queue["unsent"]
    if target["kind"] == "transaction":
        crash_point = _CRASH_POINTS[point]
        calls: list[CrashPoint] = []
        reached = injection["expectedReachability"]["value"] == "reached"

        def hook(name: CrashPoint) -> None:
            if name != crash_point:
                return
            calls.append(name)
            if reached and len(calls) == 1:
                raise _InjectedCrash(point)

        try:
            run.response = _send(run, unsent, hook=hook)
        except _InjectedCrash:
            run.response = None
            run.interrupted = True
        return len(calls)
    if target["kind"] == "client":
        if point == "V12 確認後・送信前に記録権を移す":
            run.response = _send(run, unsent, rights=DenyPrefixRights())
            return 1
        if point == "応答を端末へ返す前(ACK 消失)":
            run.response = _send(run, unsent)
            return 1
        raise AssertionError(f"未知のクライアント注入: {point}")
    run.response = _send(run, unsent)
    if point == "T7 確定後・無効化配信前":
        return 1
    if point == "消費側反映後・配信完了記録前":
        with pytest.raises(InjectedDeliveryCrash):
            deliver_pending_sync_intents(
                make_tenant_context(run.db.tenant_a),
                ConsumedThenCrashSink(run.sink),
                ChangeRights(),
            )
        return 1
    if point == "サーバー確定後・I6端末永続化前":
        return 1
    raise AssertionError(f"未知のトランザクション外注入: {point}")


def _restart(run: _Run) -> None:
    """Case の再開操作を実行する。"""
    restart = run.case["faultInjection"]["restartOperation"].get("value")
    previous = run.response
    run.previous_mapping = (
        dict(previous.temporary_id_mapping) if isinstance(previous, AckResult) else None
    )
    run.interrupted = False
    if restart == "同じ要求を再送する":
        run.response = _send(run, run.queue["unsent"])
    elif restart == "記録権を引き継ぎ、同じ要求を再送する":
        _hand_over(run)
        run.response = _send(run, run.queue["unsent"])
    elif restart == "記録権を引き継ぎ、保持端末として同じ要求を再送する":
        _hand_over(run)
        run.response = _send(run, run.queue["unsent"], rights=PrefixRights())
    elif restart == "欠落した D1 = 5 を補って再送する":
        run.response = _send(run, run.queue["restartUnsent"])
    elif restart == "配信を再実行する":
        deliver_pending_sync_intents(
            make_tenant_context(run.db.tenant_a), run.sink, ChangeRights()
        )
    elif restart == "ブラウザを再起動して端末の保持を読む":
        pass
    else:
        raise AssertionError(f"未知の再開操作: {restart}")


# ---------------------------------------------------------------- 観測


def _ledger_kind(run: _Run, d5: UUID) -> str | None:
    rows = _sql(
        run.db,
        "SELECT kind FROM idempotency_ledger WHERE tenant_id = %s AND d5 = %s",
        (run.db.tenant_a, d5),
    )
    assert len(rows) <= 1
    return rows[0][0] if rows else None


def _count(run: _Run, table: str, where: str, params: Sequence[object]) -> int:
    if table not in {
        "event_slots",
        "operation_events",
        "rejected_event_originals",
        "evacuated_event_originals",
        "temporary_player_id_mappings",
        "invalidation_intents",
        "players",
    }:
        raise ValueError("runner が観測する表でない")
    # 表名と条件は上の許可表と runner 内の固定文字列だけから作る。
    statement = cast(
        LiteralString, f"SELECT count(*) FROM {table} WHERE tenant_id = %s AND {where}"
    )
    return _sql(run.db, statement, (run.db.tenant_a, *params))[0][0]


def _watermark(run: _Run) -> int:
    return _sql(
        run.db,
        "SELECT confirmed_watermark FROM recording_generations "
        "WHERE tenant_id = %s AND game_id = %s AND generation = 1",
        (run.db.tenant_a, run.game),
    )[0][0]


def _intent_prefix(run: _Run) -> str:
    subject = run.subject()
    if run.path == "P3":
        version = subject["expectedVersion"] + 1
        return f"sync:{run.game}:1:{subject['target']['d1']}:{version}:"
    return f"sync:{run.uuid(subject['d5'])}:"


def _intent_rows(run: _Run) -> dict[str, str]:
    rows = _sql(
        run.db,
        "SELECT scope_kind, delivery_status FROM invalidation_intents "
        "WHERE tenant_id = %s AND intent_id LIKE %s",
        (run.db.tenant_a, _intent_prefix(run) + "%"),
    )
    return {scope: status for scope, status in sorted(rows)}


def _state(run: _Run, present: bool, *, writes: bool = True) -> str:
    if present:
        return "committed"
    if writes and run.interrupted:
        return "notCommitted"
    return "no-write"


def _t_elements(run: _Run) -> dict[str, object]:
    subject = run.subject()
    d5 = run.uuid(subject["d5"])
    kind = _ledger_kind(run, d5)
    accepted = kind == "accepted"
    evidence: dict[str, object] = {}
    if run.path == "P3":
        target_d1 = subject["target"]["d1"]
        version = _sql(
            run.db,
            "SELECT confirmed_version FROM event_slots WHERE tenant_id = %s "
            "AND game_id = %s AND generation = 1 AND d1 = %s",
            (run.db.tenant_a, run.game, target_d1),
        )[0][0]
        evidence = {
            "T1": accepted,
            "T2": _count(run, "operation_events", "d5 = %s", (d5,)) > 0,
            "T4": accepted and str(d5) in run.projected,
            "T6": accepted,
            "T7": {
                "targetVersion": version == subject["expectedVersion"] + 1,
                "intents": bool(_intent_rows(run)),
            },
        }
    elif run.path == "P4":
        evidence = {
            "T8": {
                "ledger": kind == "evacuated",
                "original": _count(run, "evacuated_event_originals", "d5 = %s", (d5,))
                > 0,
            }
        }
    elif run.path == "P5":
        evidence = {
            "T9": {
                "ledger": kind == "rejected",
                "original": _count(run, "rejected_event_originals", "d5 = %s", (d5,))
                > 0,
            }
        }
    else:
        event_rows = _sql(
            run.db,
            "SELECT d2 FROM operation_events WHERE tenant_id = %s AND d5 = %s",
            (run.db.tenant_a, d5),
        )
        registration = subject.get("registration")
        evidence = {
            "T1": accepted,
            "T2": {
                "slot": _count(
                    run,
                    "event_slots",
                    "game_id = %s AND generation = 1 AND d1 = %s",
                    (run.game, subject["d1"]),
                )
                > 0,
                "event": bool(event_rows),
            },
            "T3": accepted and _watermark(run) >= subject["d1"],
            "T4": accepted and str(d5) in run.projected,
            "T5": bool(event_rows) and event_rows[0][0] is not None,
            "T6": {
                "result": accepted,
                "mapping": registration is not None
                and _count(
                    run,
                    "temporary_player_id_mappings",
                    "temporary_id = %s",
                    (run.uuid(registration),),
                )
                > 0,
            },
        }
    record: dict[str, object] = {}
    for element in _ROUTES[run.path]:
        units = T_ELEMENT_UNITS.get((run.path, element))
        value = evidence[element]
        if units is None:
            assert isinstance(value, bool)
            record[element] = _state(run, value)
        else:
            assert isinstance(value, dict)
            record[element] = {
                unit: _state(
                    run,
                    value[unit],
                    writes=not (unit == "mapping" and "registration" not in subject),
                )
                for unit in units
            }
    return record


def _names(run: _Run) -> list[str]:
    return run.asset["input"]["d5"]["value"]["requested"]


def _idempotent_result(run: _Run) -> dict[str, object]:
    response = run.response
    boundary: str | None = None
    branch: str | None = None
    if isinstance(response, AckResult):
        boundary, branch = response.boundary, response.b3_branch
    elif isinstance(response, (AcceptedChangeResult, RejectedChangeResult)):
        boundary = response.boundary
    elif isinstance(response, str):
        boundary = response
    return {
        "boundary": boundary,
        "b3Branch": branch,
        "ledger": {name: _ledger_kind(run, run.uuid(name)) for name in _names(run)},
        "originals": {
            name: _count(run, "rejected_event_originals", "d5 = %s", (run.uuid(name),))
            + _count(run, "evacuated_event_originals", "d5 = %s", (run.uuid(name),))
            for name in _names(run)
        },
    }


def _mapping(run: _Run) -> dict[str, object]:
    temporary = {
        str(run.uuid(event["registration"])): event["registration"]
        for event in [*run.queue["unsent"], *run.queue.get("restartUnsent", [])]
        if "registration" in event
    }
    persisted = sorted(
        name
        for key, name in temporary.items()
        if _count(run, "temporary_player_id_mappings", "temporary_id = %s", (key,))
    )
    current = (
        dict(run.response.temporary_id_mapping)
        if isinstance(run.response, AckResult)
        else {}
    )
    same: bool | None = None
    if current and run.previous_mapping:
        same = current == run.previous_mapping
    return {
        "persisted": persisted,
        "acknowledged": sorted(temporary.get(key, key) for key in current),
        "players": _count(run, "players", "name = %s", (_REGISTERED_NAME,)),
        "sameAsPreviousResponse": same,
    }


def _replay_counts(run: _Run) -> tuple[dict[str, int], dict[str, int]]:
    """保存済み結果の再掲と全件重複を実際に送り、範囲ごとの意図件数を返す。"""
    request = run.last_request
    assert request is not None
    counts: list[dict[str, int]] = []
    for _ in range(2):
        if run.path == "P3":
            _send(run, run.queue["unsent"])
        else:
            events = run.queue.get("restartUnsent") or run.queue["unsent"]
            _send(run, events, rights=PrefixRights())
        rows = _sql(
            run.db,
            "SELECT scope_kind, count(*) FROM invalidation_intents "
            "WHERE tenant_id = %s AND intent_id LIKE %s GROUP BY scope_kind",
            (run.db.tenant_a, _intent_prefix(run) + "%"),
        )
        counts.append({scope: count for scope, count in sorted(rows)})
    return counts[0], counts[1]


def _observe(run: _Run, expected: Mapping[str, Any]) -> dict[str, object]:
    """観測点の実値フィールドを、資産のフィールド集合の順で読む。"""
    real = [key for key, value in expected.items() if "omittedBecause" not in value]
    rows = _intent_rows(run)
    observed: dict[str, object] = {
        "d1": {
            "ack": [[item.d1, item.state] for item in run.response.a5]
            if isinstance(run.response, AckResult)
            else None
        },
        "prefix": {"d3": _watermark(run)},
        "idempotentResult": _idempotent_result(run),
        "recordingRight": {"held": run.rights_verdict},
        "tElementCommitment": _t_elements(run),
        "invalidationIntentIds": {"scopes": sorted(rows)},
        "invalidationIntentRows": rows,
        "recoveryGenerationCheck": {"current": run.recovery_verdict},
        "deliveryState": {
            "attempted": sum(
                1 for call in run.sink.calls if call.startswith(_intent_prefix(run))
            )
        },
        "consumerReflectionState": {
            "effects": sum(
                1
                for effect in run.sink.effects
                if effect.startswith(_intent_prefix(run))
            ),
            "redelivered": sum(
                1
                for intent_id in set(run.sink.calls)
                if intent_id.startswith(_intent_prefix(run))
                and run.sink.calls.count(intent_id) > 1
            ),
        },
        "deliveryCompletionRecord": {
            "delivered": sum(1 for status in rows.values() if status == "delivered")
        },
    }
    if "temporaryIdMapping" in real:
        observed["temporaryIdMapping"] = _mapping(run)
    if "intentCountsAfterReplay" in real:
        replay, duplicate = _replay_counts(run)
        observed["intentCountsAfterReplay"] = replay
        observed["intentCountsAfterFullDuplicate"] = duplicate
    return {key: observed[key] for key in real}


def _run_case(
    db: _SyncDatabase,
    asset: Mapping[str, Any],
    case: Mapping[str, Any],
    mutate: Callable[[_Run], None] | None = None,
) -> tuple[dict[str, Any], frozenset[str]]:
    """1 case を実行し、結果と、クライアント runner が観測するフィールドを返す。

    ``mutate`` は負例の試験だけが渡し、注入の直後に DB を壊す。
    """
    run = _Run(db, asset, case)
    cleanups: list[Callable[[], Any]] = []
    try:
        _seed(run, cleanups)
        excluded = CLIENT_OBSERVED_FIELDS.get((asset["scenarioId"], case["caseId"]), ())
        observations = case["observations"]
        hook_calls = _inject(run)
        if mutate is not None:
            mutate(run)

        def visible(expected: Mapping[str, Any]) -> dict[str, Any]:
            return {k: v for k, v in expected["fields"].items() if k not in excluded}

        results = [
            {
                "observationPoint": observations[0]["observationPoint"],
                "fields": _observe(run, visible(observations[0])),
            }
        ]
        if len(observations) == 2:
            _restart(run)
            results.append(
                {
                    "observationPoint": observations[1]["observationPoint"],
                    "fields": _observe(run, visible(observations[1])),
                }
            )
        assert len(observations) <= 2
        return {
            "scenarioId": asset["scenarioId"],
            "cases": [
                {
                    "caseId": case["caseId"],
                    "hookCalls": hook_calls,
                    "observations": results,
                }
            ],
        }, frozenset(excluded)
    finally:
        for cleanup in reversed(cleanups):
            cleanup()


@pytest.mark.parametrize(("asset", "case"), _SERVER_CASES)
def test_server_failure_scenario_case(
    prefix_database: _SyncDatabase, asset: dict[str, Any], case: dict[str, Any]
) -> None:
    """サーバー側の資産の各 case を公開入口で実行し、結果検査を通す。"""
    result, excluded = _run_case(prefix_database, asset, case)
    validate_failure_scenario_result(
        asset,
        result,
        _ROUTES,
        case_ids=[case["caseId"]],
        excluded_field_ids=excluded,
    )


def test_partial_commit_state_is_red(
    prefix_database: _SyncDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """負例: DB を部分確定にする変異(確定後にイベント行だけを消す)は赤になる。

    T2 の注入点で落ちたはずの送信を、変異では確定させてから T2 のイベント行だけを
    消す。台帳(T1・T6)は残り、イベント(T2)だけが欠けた状態を runner が観測し、
    結果検査が部分確定として拒否する。
    """
    monkeypatch.setitem(_CRASH_POINTS, "T2 の保存後・コミット前", "after_transaction")
    asset = next(a for a in _SERVER_ASSETS if a["scenarioId"] == "p1-crash-boundaries")
    case = next(c for c in asset["cases"] if c["caseId"] == "crash-t2")

    def drop_event_row(run: _Run) -> None:
        _execute(
            run.db,
            "DELETE FROM operation_events WHERE tenant_id = %s AND d5 = %s",
            (run.db.tenant_a, run.uuid(run.queue["subject"])),
        )

    result, excluded = _run_case(prefix_database, asset, case, drop_event_row)
    with pytest.raises(FailureScenarioContractError, match="部分確定"):
        validate_failure_scenario_result(
            asset,
            result,
            _ROUTES,
            case_ids=[case["caseId"]],
            excluded_field_ids=excluded,
        )


def test_runner_split_covers_every_case_and_field() -> None:
    """サーバー runner とクライアント runner の担当の和が、全資産の全 case になる。"""
    assets = dict((asset["scenarioId"], asset) for _, asset in _assets())
    assert set(assets) == OWNED_SCENARIO_IDS
    for (scenario_id, case_id), fields in CLIENT_OBSERVED_FIELDS.items():
        case = next(c for c in assets[scenario_id]["cases"] if c["caseId"] == case_id)
        for observation in case["observations"]:
            real = {
                key
                for key, value in observation["fields"].items()
                if not (isinstance(value, dict) and "omittedBecause" in value)
            }
            # 端末を観測するのは I6 の実値フィールドちょうど(frontend の
            # CLIENT_OBSERVED_CASES も同じ資産から同じ集合を照合する)。
            assert fields == {key for key in real if key.startswith("i6")}
    server_cases = {
        (asset["scenarioId"], case["caseId"]) for asset, case in _SERVER_CASE_PAIRS
    }
    assert set(CLIENT_OBSERVED_FIELDS) <= server_cases
