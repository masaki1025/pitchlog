"""合成row readerと実artifactの橋。認可/実DB保存/Port登録の証明ではない。"""

from __future__ import annotations

import json
import traceback
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_started_snapshot import Bundle

from pitchlog.domainrt.first_pitch_continuation import (
    CombinedRequest,
    evaluate_first_pitch_with_continuation,
)
from pitchlog.domainrt.host import NodeDomainHost
from pitchlog.repositories import transaction
from pitchlog.repositories.context import _ISSUANCE_CAPABILITY, TenantContext
from pitchlog.repositories.started_snapshot import read_initial_started_snapshot
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync import first_ball_bridge as api
from pitchlog.sync.first_ball_frame import (
    FirstBallBridge,
    FirstBallFrame,
    FirstBallFrameError,
    FirstBallIntent,
)
from pitchlog.sync.idempotency import operation_fingerprint
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import _issue_port_writer

ROOT = Path(__file__).resolve().parents[2]
SHA = json.loads((ROOT / "frontend/public/domain/pitchlog-domain.json").read_text())[
    "sha256"
]
INTENT = FirstBallIntent("batting-result", "batting-result.ball", "pitch-event")


class _TransactionDouble:
    """実SessionTransactionと同様にobject identityで比較する。"""

    def __init__(self):
        self.is_active = True


@pytest.fixture
def rig(monkeypatch: pytest.MonkeyPatch):
    """実DBなしの保存rowと、既handle/実writer型のpure接続を作る。"""
    rows = Bundle()
    handle = rows.handle
    context = TenantContext(rows.tenant, _ISSUANCE_CAPABILITY)
    handle._context = context
    handle._bound_integrity_proof = context._integrity_proof
    tx = _TransactionDouble()
    session = SimpleNamespace(current=tx, nested=False)
    session.get_transaction = lambda: session.current
    session.in_nested_transaction = lambda: session.nested
    monkeypatch.setitem(
        transaction._TRANSACTION_RUNTIMES, handle._state_key, (session, object())
    )
    monkeypatch.setattr(
        transaction._TenantTransaction,
        "run",
        lambda owner, token: rows.run(owner, token),
    )
    writer = _issue_port_writer(handle.run)
    event = SyncEvent(
        str(uuid4()),
        str(rows.game_id),
        1,
        "opaque-d4",
        "1",
        0,
        {"resultId": "batting-result.ball"},
        {"input": "unmapped-v8"},
    )
    rig = SimpleNamespace(
        rows=rows,
        handle=handle,
        writer=writer,
        event=event,
        key=handle._state_key,
        context=context,
        session=session,
        tx=tx,
    )
    yield rig
    writer._close()
    api._STATES.clear()
    api._ATTEMPTED.clear()


@contextmanager
def bound(rig):
    """既適用印の内側だけで待機bridgeをbindする。"""
    with transaction._sync_apply_active():
        with api._bind_first_ball_at_content_stage(
            rig.handle, rig.writer, rig.event
        ) as bridge:
            yield bridge


def evaluate(bridge, rig, **kwargs):
    """評価の全入力を隠さずprivate bridgeへ渡す。"""
    return api.evaluate_first_ball_frame(
        bridge,
        kwargs.pop("intent", INTENT),
        writer=kwargs.pop("writer", rig.writer),
        event=kwargs.pop("event", rig.event),
        expected_artifact_sha256=kwargs.pop("sha", SHA),
        **kwargs,
    )


def consume(bridge, frame, rig, **kwargs):
    """消費のwriter/eventを試験で明示的に差し替えられる補助。"""
    return api.consume_first_ball_frame(
        bridge,
        frame,
        writer=kwargs.get("writer", rig.writer),
        event=kwargs.get("event", rig.event),
    )


def assert_fixed(error):
    """元例外と資格候補を通常の失敗表示へ出さない。"""
    assert error.value.args == ("初球の同一評価frameを利用できません",)
    assert "PRIVATE_CANARY" not in "".join(traceback.format_exception(error.value))


def test_waiting_bind_does_not_read_or_evaluate(rig, monkeypatch):
    """bindだけで実snapshotや数学を前倒ししない。"""
    monkeypatch.setattr(api, "open_domain_host", lambda: pytest.fail("early host"))
    monkeypatch.setattr(
        api, "read_initial_started_snapshot", lambda *a: pytest.fail("early read")
    )
    with bound(rig) as bridge:
        assert rig.rows.calls == []
        with pytest.raises(FirstBallFrameError):
            consume(bridge, object.__new__(FirstBallFrame), rig)


@pytest.mark.parametrize("regulation,limit", [(7, None), (9, None), (9, 9)])
def test_real_reader_and_one_host_match_existing_caller(
    rig, monkeypatch, regulation, limit
):
    """既readerと三規則familyを使い、同host一回の値を既callerと全比較する。"""
    rig.rows.game["applied_rules"]["regulationInnings"] = regulation
    rig.rows.game["applied_rules"]["extensionLimit"] = limit
    snapshot = read_initial_started_snapshot(rig.handle, rig.rows.game_id)
    request = CombinedRequest.model_validate_json(
        json.dumps(
            {
                "t1": {
                    "eventKind": INTENT.event_kind,
                    "resultId": INTENT.result_id,
                    "pitchEventKind": INTENT.pitch_event_kind,
                    "before": snapshot.before.model_dump(mode="json", by_alias=True),
                },
                "rules": snapshot.rules.model_dump(mode="json", by_alias=True),
            }
        )
    )
    expected = evaluate_first_pitch_with_continuation(request)
    assert expected.ok is True
    rig.rows.calls.clear()
    opened, called = [], []
    original_open, original_call = api.open_domain_host, NodeDomainHost.call

    @contextmanager
    def spy_open():
        with original_open() as host:
            opened.append(host)
            yield host

    def spy_call(host, operation, payload):
        if operation == "deriveFirstPitchWithContinuation":
            called.append((host, payload))
        return original_call(host, operation, payload)

    monkeypatch.setattr(api, "open_domain_host", spy_open)
    monkeypatch.setattr(NodeDomainHost, "call", spy_call)
    original = operation_fingerprint(rig.event, "P2", None)
    with bound(rig) as bridge:
        assert not rig.rows.calls
        frame = evaluate(bridge, rig)
        value = consume(bridge, frame, rig)
        assert len(opened) == len(called) == 1 and called[0][0] is opened[0]
        assert json.loads(value.request_json) == request.model_dump(
            mode="json", by_alias=True
        )
        assert json.loads(value.response_json) == expected.model_dump(
            mode="json", by_alias=True
        )
        assert json.loads(value.roster_json) == snapshot.roster.model_dump(
            mode="json", by_alias=True
        )
        assert value.source_fingerprint == original and value.artifact_sha256 == SHA
        assert value.tenant_id == rig.rows.tenant and value.game_id == rig.rows.game_id
        with pytest.raises(FirstBallFrameError):
            consume(bridge, frame, rig)
    assert operation_fingerprint(rig.event, "P2", None) == original
    assert not api._STATES


@pytest.mark.parametrize(
    "fault",
    [
        "no-apply",
        "no-runtime",
        "writer-closed",
        "other-writer",
        "other-executor",
        "bad-context",
        "bad-event",
    ],
)
def test_invalid_binding_never_reads_or_opens_host(rig, monkeypatch, fault):
    """scope/tenant/writerの不一致をreadより先に拒否する。"""
    writer = rig.writer
    if fault == "no-runtime":
        monkeypatch.delitem(transaction._TRANSACTION_RUNTIMES, rig.key)
    elif fault == "writer-closed":
        writer._close()
    elif fault == "other-writer":
        writer = _issue_port_writer(lambda token: TenantOperationResult(()))
    elif fault == "other-executor":
        writer._execute = lambda token: None
    elif fault == "bad-context":
        rig.handle._bound_tenant_id = uuid4()
    elif fault == "bad-event":
        rig.event = replace(rig.event, v5="play_input")
    monkeypatch.setattr(api, "open_domain_host", lambda: pytest.fail("host"))
    with pytest.raises(FirstBallFrameError) as error:
        if fault == "no-apply":
            with api._bind_first_ball_at_content_stage(rig.handle, writer, rig.event):
                pytest.fail("bound")
        else:
            with transaction._sync_apply_active():
                with api._bind_first_ball_at_content_stage(
                    rig.handle, writer, rig.event
                ):
                    pytest.fail("bound")
    assert_fixed(error)
    assert rig.rows.calls == []


@pytest.mark.parametrize(
    "fault", ["writer", "handle", "runtime", "event", "d5", "tenant"]
)
def test_ready_frame_is_rejected_after_binding_changes(rig, monkeypatch, fault):
    """評価後にもlifetime/原event/tenantの変化を黙認しない。"""
    with bound(rig) as bridge:
        frame = evaluate(bridge, rig)
        if fault == "writer":
            rig.writer._close()
        elif fault == "handle":
            rig.handle._expire()
        elif fault == "runtime":
            monkeypatch.delitem(transaction._TRANSACTION_RUNTIMES, rig.key)
        elif fault == "event":
            rig.event = replace(rig.event, v7={"PRIVATE_CANARY": "changed"})
        elif fault == "d5":
            rig.event = replace(rig.event, d5=str(uuid4()))
        else:
            rig.handle._bound_tenant_id = uuid4()
        with pytest.raises(FirstBallFrameError) as error:
            consume(bridge, frame, rig)
        assert_fixed(error)


def test_forged_bridge_frame_and_post_exit_are_not_private_evidence(rig):
    """同型objectでもregistry/発行同一性が無ければ使えない。"""
    with bound(rig) as bridge:
        frame = evaluate(bridge, rig)
        with pytest.raises(FirstBallFrameError):
            evaluate(object.__new__(FirstBallBridge), rig)
        with pytest.raises(FirstBallFrameError):
            consume(bridge, object.__new__(FirstBallFrame), rig)
    with transaction._sync_apply_active():
        with pytest.raises(FirstBallFrameError):
            consume(bridge, frame, rig)


def test_duplicate_evaluation_in_one_transaction_is_rejected(rig, monkeypatch):
    """別bridgeへbindし直しても同TX/D5を再評価しない。"""
    count = []
    original = NodeDomainHost.call

    def spy(host, operation, payload):
        if operation == "deriveFirstPitchWithContinuation":
            count.append(operation)
        return original(host, operation, payload)

    monkeypatch.setattr(NodeDomainHost, "call", spy)
    with transaction._sync_apply_active():
        with api._bind_first_ball_at_content_stage(
            rig.handle, rig.writer, rig.event
        ) as first:
            evaluate(first, rig)
            with pytest.raises(FirstBallFrameError):
                evaluate(first, rig)
        with api._bind_first_ball_at_content_stage(
            rig.handle, rig.writer, rig.event
        ) as second:
            with pytest.raises(FirstBallFrameError):
                evaluate(second, rig)
    assert count == ["deriveFirstPitchWithContinuation"]


@pytest.mark.parametrize(
    "fault", ["bad-hash", "host-failure", "source-changed", "wrong-host"]
)
def test_hash_identity_host_failures_never_issue_frame(rig, monkeypatch, fault):
    """別sourceや壊れたhostから成功frameへ昇格しない。"""
    original = NodeDomainHost.call
    calls = []

    def spy(host, operation, payload):
        if operation == "deriveFirstPitchWithContinuation":
            calls.append(host)
            if fault == "host-failure":
                raise RuntimeError("PRIVATE_CANARY")
            result = original(host, operation, payload)
            if fault == "source-changed":
                host._source = "PRIVATE_CANARY"
            return result
        return original(host, operation, payload)

    monkeypatch.setattr(NodeDomainHost, "call", spy)
    if fault == "wrong-host":

        @contextmanager
        def fake_host():
            yield SimpleNamespace(
                _source=(
                    ROOT / "frontend/public/domain/pitchlog-domain.js"
                ).read_text(),
                call=lambda *args: json.dumps(
                    json.loads(
                        (
                            ROOT
                            / "contracts/state-transition"
                            / "t2_first_pitch_continuation_cases_v1.json"
                        ).read_text()
                    )["cases"][0]["expected"]
                ),
            )

        monkeypatch.setattr(api, "open_domain_host", fake_host)
    with bound(rig) as bridge:
        with pytest.raises(FirstBallFrameError) as error:
            evaluate(bridge, rig, sha="f" * 64 if fault == "bad-hash" else SHA)
        assert_fixed(error)
        assert api._STATES[bridge].frame is None
        if fault in ("bad-hash", "wrong-host"):
            assert not calls


@pytest.mark.parametrize("fault", ["partial-t2", "unsupported-t1", "nonempty"])
def test_non_success_never_becomes_a_frame(rig, fault):
    """T2未評価/未対応T1/既記録ありを保存可能に見せない。"""
    intent = INTENT
    if fault == "partial-t2":
        rig.rows.game["applied_rules"]["regulationInnings"] = 8
    elif fault == "unsupported-t1":
        intent = FirstBallIntent(
            "batting-result", "batting-result.called-pitch", "pitch-event"
        )
    else:
        from pitchlog.repositories.started_snapshot_operations import (
            StartedPlayRowsExistenceToken,
        )

        rig.rows.nonempty = StartedPlayRowsExistenceToken
    with bound(rig) as bridge:
        with pytest.raises(FirstBallFrameError):
            evaluate(bridge, rig, intent=intent)
        assert api._STATES[bridge].value is None


def test_caller_failure_propagates_unchanged_and_expires_the_registry(rig):
    """O4/DB故障の元例外を独自の拒否へ変換しない。"""
    fault = RuntimeError("original failure")
    with pytest.raises(RuntimeError) as error:
        with bound(rig) as bridge:
            evaluate(bridge, rig)
            raise fault
    assert error.value is fault and not api._STATES


def test_no_external_success_bool_callback_or_host_is_an_api_parameter():
    """未接続の先行権利判定を引数のTrueで成立させる入口を作らない。"""
    import inspect

    parameters = set(inspect.signature(api.evaluate_first_ball_frame).parameters)
    assert parameters == {
        "bridge",
        "intent",
        "writer",
        "event",
        "expected_artifact_sha256",
    }


@pytest.mark.parametrize("point", ["after-read", "after-call"])
def test_lifetime_fault_during_evaluation_cannot_issue_frame(rig, monkeypatch, point):
    """評価の途中で失効した実writer対応を、事前確認だけで受け入れない。"""
    original_read, original_call = (
        api.read_initial_started_snapshot,
        NodeDomainHost.call,
    )
    calls = []

    def read(handle, game_id):
        snapshot = original_read(handle, game_id)
        if point == "after-read":
            rig.handle._expire()
        return snapshot

    def call(host, operation, payload):
        result = original_call(host, operation, payload)
        if operation == "deriveFirstPitchWithContinuation":
            calls.append(host)
            if point == "after-call":
                transaction._TRANSACTION_RUNTIMES.pop(rig.key)
        return result

    monkeypatch.setattr(api, "read_initial_started_snapshot", read)
    monkeypatch.setattr(NodeDomainHost, "call", call)
    with bound(rig) as bridge:
        with pytest.raises(FirstBallFrameError):
            evaluate(bridge, rig)
        assert api._STATES[bridge].frame is None
        assert len(calls) == (1 if point == "after-call" else 0)


def test_a_different_real_writer_for_the_same_handle_cannot_consume(rig):
    """同じscopeの別PortWriterも元の発行writerではない。"""
    with bound(rig) as bridge:
        frame = evaluate(bridge, rig)
        other = _issue_port_writer(rig.handle.run)
        try:
            with pytest.raises(FirstBallFrameError):
                consume(bridge, frame, rig, writer=other)
        finally:
            other._close()


def _change_actual_transaction(rig, fault):
    """実Sessionと同じgetter/identityでTXの終了/失活/差替/nestedを表す。"""
    if fault == "ended":
        rig.session.current = None
    elif fault == "inactive":
        rig.tx.is_active = False
    elif fault == "replaced":
        rig.session.current = _TransactionDouble()
    else:
        rig.session.nested = True


@pytest.mark.parametrize("fault", ["ended", "inactive", "replaced", "nested"])
@pytest.mark.parametrize(
    "point", ["before-bind", "after-read", "after-call", "before-consume"]
)
def test_real_top_level_transaction_lifetime_changes_are_rejected(
    rig,
    monkeypatch,
    fault,
    point,
):
    """runtime/key/writerを保持したまま実TXだけ変わるP1反例を拒否する。"""
    original_read, original_call = (
        api.read_initial_started_snapshot,
        NodeDomainHost.call,
    )
    call_count = []
    owner = rig.handle._writer_lifetime()

    def read(handle, game_id):
        snapshot = original_read(handle, game_id)
        if point == "after-read":
            _change_actual_transaction(rig, fault)
        return snapshot

    def call(host, operation, payload):
        result = original_call(host, operation, payload)
        if operation == "deriveFirstPitchWithContinuation":
            call_count.append(host)
            if point == "after-call":
                _change_actual_transaction(rig, fault)
        return result

    monkeypatch.setattr(api, "read_initial_started_snapshot", read)
    monkeypatch.setattr(NodeDomainHost, "call", call)
    if point == "before-bind":
        _change_actual_transaction(rig, fault)
        if fault == "replaced":
            # bind前なら別active TX自体は新しい現在TX。旧ownerへ転用はしない。
            assert rig.handle._writer_lifetime() != owner
            with bound(rig) as bridge:
                frame = evaluate(bridge, rig)
                consume(bridge, frame, rig)
            return
        with pytest.raises(FirstBallFrameError):
            with bound(rig):
                pytest.fail("inactive top-level TX bound")
        assert not rig.rows.calls and not call_count
        return
    with bound(rig) as bridge:
        with pytest.raises(FirstBallFrameError):
            frame = evaluate(bridge, rig)
            if point == "before-consume":
                _change_actual_transaction(rig, fault)
                consume(bridge, frame, rig)
        assert api._STATES[bridge].frame is None
    from pitchlog.repositories.binding import TenantBindingError

    with pytest.raises(TenantBindingError):
        rig.handle._assert_writer_lifetime(owner)
    assert len(call_count) == (0 if point == "after-read" else 1)


def test_initial_actor_is_not_a_normal_frame_writer(rig, monkeypatch):
    """既writer_lifetimeの初期actor拒否もそのまま再利用する。"""
    monkeypatch.setitem(
        transaction._INITIAL_ACTOR_STATES, rig.key, (object(), "business")
    )
    with pytest.raises(FirstBallFrameError):
        with bound(rig):
            pytest.fail("initial actor accepted")
    assert not rig.rows.calls


def test_e1_bridge_requires_real_source_and_rechecks_wire_fingerprint(rig, monkeypatch):
    """E1用のsource寿命対向。実issuer/実認可を成立させる試験ではない。"""
    from pitchlog.sync.source_binding import _E1CoreSource

    for invalid in (None, "wire-v1:fake", object()):
        with pytest.raises(FirstBallFrameError):
            with api._bind_e1_first_ball_at_content_stage(
                rig.handle, rig.writer, rig.event, source=invalid
            ):
                pytest.fail("偽sourceを受理")
    source = object.__new__(_E1CoreSource)
    calls = []
    fingerprint = ["wire-v1:" + "a" * 64]

    def read(owner, handle, event):
        assert owner is source and handle is rig.handle and event is rig.event
        calls.append(event.d5)
        return SimpleNamespace(event_fingerprint=fingerprint[0])

    monkeypatch.setattr(_E1CoreSource, "read", read)
    with transaction._sync_apply_active():
        with api._bind_e1_first_ball_at_content_stage(
            rig.handle, rig.writer, rig.event, source=source
        ) as bridge:
            assert api._STATES[bridge].fingerprint == fingerprint[0]
            assert api._STATES[bridge].source is source
            api._state(bridge, rig.writer, rig.event)
            fingerprint[0] = "wire-v1:" + "b" * 64
            with pytest.raises(FirstBallFrameError):
                api._state(bridge, rig.writer, rig.event)
    assert len(calls) >= 4
    assert bridge not in api._STATES
