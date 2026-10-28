"""実artifactと取引doubleで単位Aを検査する。正式issuer/実DBの成功ではない。"""

from __future__ import annotations

import json
from contextlib import contextmanager
from types import MappingProxyType, SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from test_sync_apply_first_ball_bridge import SHA
from test_sync_apply_first_ball_bridge import rig as bridge_rig

from pitchlog.domainrt.first_ball_projection import (
    FirstBallCalculationValue,
    format_first_ball_calculation,
)
from pitchlog.domainrt.first_pitch import FirstPitchRequest
from pitchlog.domainrt.first_pitch_continuation import (
    CombinedRequest,
    evaluate_first_pitch_with_continuation,
)
from pitchlog.repositories import transaction as tx
from pitchlog.repositories.started_snapshot import read_initial_started_snapshot
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync import first_ball_bridge as bridge
from pitchlog.sync import first_ball_execution as api
from pitchlog.sync.control_provider import writer_binding
from pitchlog.sync.first_ball_payload import (
    FirstBallObservations,
    FirstBallParticipants,
    format_first_ball_payload,
)
from pitchlog.sync.first_ball_ports import FirstBallContentValidationPort
from pitchlog.sync.idempotency import operation_fingerprint
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import _issue_port_writer
from pitchlog.sync.source_binding import _E1CoreSource
from pitchlog.sync.tokens import (
    EventSlotReadToken,
    OperationEventReadToken,
    PortValidateFirstBallToken,
)


@pytest.fixture
def rig(monkeypatch):
    """既真正型handleを再利用する。bound/source発行は明示したpure double。"""
    generator = cast(Any, bridge_rig).__wrapped__(monkeypatch)
    r = next(generator)

    def run(handle, operation):
        if tx._is_port_command(operation):
            return tx._execute_port_command(handle, operation)
        if type(operation) in (EventSlotReadToken, OperationEventReadToken):
            return TenantOperationResult(())
        return r.rows.run(handle, operation)

    monkeypatch.setattr(tx._TenantTransaction, "run", run)
    r.writer._close()
    r.writer = _issue_port_writer(r.handle.run)
    with tx._sync_apply_active():
        snapshot = read_initial_started_snapshot(r.handle, r.rows.game_id)
    request = CombinedRequest(
        t1=FirstPitchRequest(
            eventKind="batting-result",
            resultId="batting-result.ball",
            pitchEventKind="pitch-event",
            before=snapshot.before,
        ),
        rules=snapshot.rules,
    )
    response = evaluate_first_pitch_with_continuation(request)
    assert response.ok
    calc = FirstBallCalculationValue.model_validate_json(
        format_first_ball_calculation(request, response, artifact_sha256=SHA)
    )
    people = FirstBallParticipants(
        batterId="00000000-0000-4000-8000-000000000110",
        pitcherId="00000000-0000-4000-8000-000000000201",
        catcherId="00000000-0000-4000-8000-000000000202",
        battingOrder="1",
    )
    obs = FirstBallObservations.model_validate(
        {
            "pitchTypeKey": "fastball",
            "course": {"unit": "1/263", "x": "100", "y": "120"},
            "pitchSpeed": {"kmh": None, "outsideRangeConfirmed": False},
            "stance": None,
            "battingSide": "右",
        }
    )
    v7, v8 = format_first_ball_payload(obs, people, calc)
    r.v7, r.v8 = json.loads(v7), json.loads(v8)
    r.event = SyncEvent(
        str(uuid4()), str(r.rows.game_id), 1, "opaque-d4", "1", 0, r.v7, r.v8
    )
    bound = cast(Any, object.__new__(writer_binding._LiveWriterBinding))
    bound._handle, bound._used, bound._owner = (
        r.handle,
        False,
        r.handle._writer_lifetime(),
    )
    bound._phase_snapshot = json.dumps(
        {"phase": {"wire_d4": "opaque-d4", "internal_generation": 1}}
    )
    bound._lease = SimpleNamespace(
        _phase_snapshot=bound._phase_snapshot, nonce=b"n" * 32
    )
    monkeypatch.setitem(writer_binding._LIVE_BINDINGS, r.key, bound)
    monkeypatch.setattr(
        writer_binding._LiveWriterBinding, "assert_current", lambda _: None
    )
    source = cast(Any, object.__new__(_E1CoreSource))
    source.scope, source.context, source.event = r.handle, r.context, r.event
    source.request, source.phase, source.bound = object(), object(), bound
    source.binding, source.write_started = object(), False
    r.view = SimpleNamespace(event_fingerprint="wire-v1:" + "b" * 64)
    monkeypatch.setattr(_E1CoreSource, "read", lambda self, scope, event: r.view)
    r.bound, r.source = bound, source
    try:
        yield r
    finally:
        r.writer._close()
        api._EXECUTIONS.clear()
        generator.close()


@contextmanager
def prepared(rig):
    """既適用印の内側だけで、⑦の核の準備を実行する。"""
    with tx._sync_apply_active():
        with api._bind_first_ball_execution(
            rig.handle, rig.writer, rig.event, rig.source
        ):
            yield


def validate(rig):
    """実content phaseとwriter.runを通す。"""
    with tx._port_predecision_phase(rig.handle, "content"):
        return FirstBallContentValidationPort().validate(rig.event, rig.writer)


def test_real_pair_once_ready_read_never_consumes_and_projection_is_not_supplied(
    rig, monkeypatch
):
    """実pair全値を保持しても、投影未供給を保存成功にはしない。"""
    opened = []
    original = bridge.open_domain_host

    def host():
        opened.append(True)
        return original()

    monkeypatch.setattr(bridge, "open_domain_host", host)
    with prepared(rig):
        assert validate(rig) == (True, None)
        state = cast(Any, api._EXECUTIONS[rig.key])
        assert state.payload.v7.model_dump(mode="json", by_alias=True) == rig.v7
        assert state.payload.v8.model_dump(mode="json", by_alias=True) == rig.v8
        a = bridge._read_ready_first_ball_frame(
            state.bridge, state.frame, writer=rig.writer, event=rig.event
        )
        b = bridge._read_ready_first_ball_frame(
            state.bridge, state.frame, writer=rig.writer, event=rig.event
        )
        assert a == b and a is not b
        # 旧P2再計算とは異なるE1実wireの同一指紋をframeへ保持する。
        assert a.source_fingerprint == rig.view.event_fingerprint
        assert a.source_fingerprint != operation_fingerprint(rig.event, "P2", None)
        assert bridge._STATES[state.bridge].source is rig.source
        assert bridge._STATES[state.bridge].phase == "ready"
        assert validate(rig) == (True, None) and opened == [True]
        with pytest.raises(api.FirstBallExecutionError):
            api._require_first_ball_projection_completed(rig.handle, rig.event)
    assert not api._EXECUTIONS and not bridge._STATES
    with pytest.raises(RuntimeError):
        validate(rig)


@pytest.mark.parametrize("kind", ["empty", "after", "people", "difference", "artifact"])
def test_payload_mismatch_is_only_fixed_content_false(rig, kind):
    """保存観測/計算/名簿の不一致を既内容拒否へ写す。"""
    v7, v8 = rig.v7, rig.v8
    if kind == "empty":
        v7 = {}
    elif kind == "after":
        v7["calculation"]["response"]["value"]["t1"]["after"]["stateFields"][
            "state.count.balls"
        ] = "2"
    elif kind == "people":
        v7["participants"]["batterId"] = str(uuid4())
    elif kind == "difference":
        v8["stateFields"]["state.count.balls"]["after"] = "2"
    elif kind == "artifact":
        v7["calculation"]["artifactSha256"] = "0" * 64
    rig.event = SyncEvent(
        rig.event.d5, rig.event.game_id, 1, "opaque-d4", "1", 0, v7, v8
    )
    rig.source.event = rig.event
    with prepared(rig):
        assert validate(rig) == (False, api._REASON)
    assert not api._EXECUTIONS and not bridge._STATES


@pytest.mark.parametrize(
    "field",
    [
        "nonce",
        "lease",
        "snapshot",
        "phase",
        "fingerprint",
        "source",
        "runtime",
        "writer",
    ],
)
def test_actual_scope_and_nonce_cannot_be_replaced(rig, field, monkeypatch):
    """scope不正を恒久拒否へ畳まず例外にする。"""
    with prepared(rig):
        if field == "nonce":
            rig.bound._lease.nonce = b"x" * 32
        elif field == "lease":
            rig.bound._lease = SimpleNamespace(**vars(rig.bound._lease))
        elif field == "snapshot":
            rig.bound._lease._phase_snapshot += " "
        elif field == "phase":
            rig.source.phase = object()
        elif field == "fingerprint":
            rig.view.event_fingerprint = "wire-v1:" + "x" * 64
        elif field == "source":
            rig.source.event = SyncEvent(rig.event.d5, rig.event.game_id, 1)
        elif field == "runtime":
            monkeypatch.setitem(
                tx._TRANSACTION_RUNTIMES, rig.key, (rig.session, object())
            )
        elif field == "writer":
            rig.writer._close()
        with pytest.raises(RuntimeError):
            validate(rig)
    assert not api._EXECUTIONS and not bridge._STATES


def test_same_keys_clone_or_wrong_phase_has_no_ready_authority(rig):
    """同値DTOや別phaseは元contextを借りられない。"""
    with prepared(rig):
        clone = SyncEvent(
            rig.event.d5, rig.event.game_id, 1, "opaque-d4", "1", 0, rig.v7, rig.v8
        )
        with tx._port_predecision_phase(rig.handle, "content"):
            with pytest.raises(api.FirstBallExecutionError):
                FirstBallContentValidationPort().validate(clone, rig.writer)
        with tx._port_predecision_phase(rig.handle, "rights"):
            with pytest.raises(RuntimeError):
                FirstBallContentValidationPort().validate(rig.event, rig.writer)
        assert validate(rig) == (True, None)


def test_host_fault_propagates_and_invalidates(rig, monkeypatch):
    """host故障をpartial成功や恒久拒否にしない。"""

    def fail():
        raise RuntimeError("PRIVATE_CANARY")

    monkeypatch.setattr(bridge, "open_domain_host", fail)
    with pytest.raises(RuntimeError):
        with prepared(rig):
            pytest.fail("host故障でready")
    assert not api._EXECUTIONS and not bridge._STATES


def test_nested_or_handmade_command_is_rejected(rig):
    """外部からcontextの再発行や同型参照の偽造をしない。"""
    with prepared(rig):
        with pytest.raises(RuntimeError):
            with api._bind_first_ball_execution(
                rig.handle, rig.writer, rig.event, rig.source
            ):
                pytest.fail("nested")
        with tx._port_predecision_phase(rig.handle, "content"):
            subtype = type("ForgedContent", (PortValidateFirstBallToken,), {})
            with pytest.raises(RuntimeError):
                rig.writer.run(
                    subtype(
                        UUID(rig.event.game_id),
                        UUID(rig.event.d5),
                        rig.event,
                        rig.writer,
                    )
                )
    assert not api._EXECUTIONS


def test_another_writer_for_same_handle_cannot_borrow_context(rig):
    """同handleの別writer参照も、元writerへ昇格しない。"""
    with prepared(rig):
        other = _issue_port_writer(rig.handle.run)
        try:
            with tx._port_predecision_phase(rig.handle, "content"):
                with pytest.raises(api.FirstBallExecutionError):
                    FirstBallContentValidationPort().validate(rig.event, other)
            assert validate(rig) == (True, None)
        finally:
            other._close()


@pytest.mark.parametrize(
    "kind",
    [
        "unsupported",
        "input-scope",
        "evaluation-fault",
        "invalid-request",
        "unknown",
        "bad-json",
    ],
)
def test_known_scope_rejection_is_separate_from_host_or_unknown_failure(
    rig, kind, monkeypatch
):
    """既scope非対応だけFalseとし、評価不能/内部不正/未知応答はrollbackする。"""
    original = bridge.NodeDomainHost.call

    def response(host, operation, request):
        if operation != "deriveFirstPitchWithContinuation":
            return original(host, operation, request)
        if kind == "unsupported":
            return json.dumps({"ok": False, "error": {"code": "UNSUPPORTED_T1_SCOPE"}})
        if kind == "invalid-request":
            return json.dumps({"ok": False, "error": {"code": "INVALID_REQUEST"}})
        if kind in ("input-scope", "evaluation-fault"):
            return json.dumps(
                {
                    "ok": False,
                    "error": {"code": "T2_NOT_EVALUATED"},
                    "value": {
                        "t1": rig.v7["calculation"]["response"]["value"]["t1"],
                        "t2": {
                            "kind": "not-evaluated",
                            "reason": "input-not-in-closed-unit"
                            if kind == "input-scope"
                            else "evaluation-unavailable",
                        },
                    },
                }
            )
        return "{}" if kind == "unknown" else "NOT_JSON"

    monkeypatch.setattr(bridge.NodeDomainHost, "call", response)
    if kind in ("unsupported", "input-scope"):
        with prepared(rig):
            assert validate(rig) == (False, api._REASON)
    else:
        with pytest.raises(RuntimeError):
            with prepared(rig):
                pytest.fail("faultをreadyに変換")
    assert not api._EXECUTIONS and not bridge._STATES


def test_ready_clone_mutation_cannot_change_stored_frame_and_stale_frame_rejects(rig):
    """返却複製の改変は本体へ届かず、一度失効したframeを再承認しない。"""
    with prepared(rig):
        state = cast(Any, api._EXECUTIONS[rig.key])
        value = bridge._read_ready_first_ball_frame(
            state.bridge, state.frame, writer=rig.writer, event=rig.event
        )
        original = value.request_json
        object.__setattr__(value, "request_json", "MUTATED")
        assert (
            bridge._read_ready_first_ball_frame(
                state.bridge, state.frame, writer=rig.writer, event=rig.event
            ).request_json
            == original
        )
        with pytest.raises(RuntimeError):
            bridge._read_ready_first_ball_frame(
                state.bridge, cast(Any, object()), writer=rig.writer, event=rig.event
            )
        with pytest.raises(RuntimeError):
            validate(rig)


@pytest.mark.parametrize(
    "stage", ["replay", "conflict", "rights", "gap", "confirmed", "w2", "content", "o4"]
)
def test_prefix_keeps_prior_rejections_before_host_and_closes_context(
    rig, stage, monkeypatch
):
    """実局所kernelの拒否順を、DB/issuer/権利double資格で合成照合する。"""
    from pitchlog.sync import prefix_path
    from pitchlog.sync.idempotency import D5Candidate, StoredResult

    opened = []
    original = bridge.open_domain_host

    def host():
        opened.append(True)
        return original()

    monkeypatch.setattr(bridge, "open_domain_host", host)
    monkeypatch.setattr(
        prefix_path,
        "_lock_game_generation",
        lambda *args: (1, 1 if stage == "confirmed" else 0),
    )
    if stage == "replay":
        candidate = D5Candidate(
            "stored_result",
            stored=StoredResult(
                "accepted",
                rig.view.event_fingerprint,
                {
                    "state": "受理",
                    "d3": 1,
                    "temporary_id_mapping": MappingProxyType({}),
                },
                None,
            ),
        )
    elif stage == "conflict":
        candidate = D5Candidate("conflict", boundary="B3b")
    else:
        candidate = D5Candidate("unused")
    monkeypatch.setattr(prefix_path, "classify_d5", lambda *args: candidate)
    monkeypatch.setattr(
        prefix_path.port_guard, "require_registered_port", lambda _: None
    )

    class Rights:
        def holds_recording_right(self, *args):
            return stage != "rights"

    class Projection:
        def apply(self, *args):
            pytest.fail("単位Aの投影到達")

    v7 = {} if stage == "content" else rig.v7
    v9 = {"unknown": "value"} if stage == "w2" else prefix_path.ABSENT
    rig.event = SyncEvent(
        rig.event.d5,
        rig.event.game_id,
        2 if stage == "gap" else 1,
        "opaque-d4",
        "1",
        0,
        v7,
        rig.v8,
        v9,
    )
    rig.source.event = rig.event
    with tx._sync_apply_active():

        def action():
            return prefix_path._apply_locked_in_scope(
                rig.handle,
                rig.event,
                cast(Any, Rights()),
                cast(Any, Projection()),
                FirstBallContentValidationPort(),
                "proof",
                None,
                None,
                source=rig.source,
                path="P2",
                order_resolver=lambda *args: None,
                writer=rig.writer,
            )

        if stage in ("rights", "confirmed", "w2", "content"):
            with pytest.raises(prefix_path.P1PreconditionError):
                action()
        elif stage == "o4":
            with pytest.raises(prefix_path._NoWriteStop):
                action()
        else:
            result = action()
            assert (
                result.replayed
                if stage == "replay"
                else result.boundary in ("B3b", "B2")
            )
    assert opened == ([True] if stage == "o4" else [])
    assert not api._EXECUTIONS and not bridge._STATES


def test_projection_completion_cannot_be_asserted_without_private_context(rig):
    """context不在を成功へ補完しない。"""
    with tx._sync_apply_active():
        with pytest.raises(api.FirstBallExecutionError):
            api._require_first_ball_projection_completed(rig.handle, rig.event)


@pytest.mark.parametrize("field", ["game_id", "d5"])
def test_command_force_changed_uuid_subclass_rejected_at_use(rig, field):
    """凍結命令を強制改変しても、等値UUID派生型を資格にしない。"""

    class DerivedUUID(UUID):
        pass

    with prepared(rig):
        command = PortValidateFirstBallToken(
            UUID(rig.event.game_id), UUID(rig.event.d5), rig.event, rig.writer
        )
        original = getattr(command, field)
        forged = DerivedUUID(str(original))
        assert forged == original and type(forged) is not UUID
        object.__setattr__(command, field, forged)
        with tx._port_predecision_phase(rig.handle, "content"):
            with pytest.raises(api.FirstBallExecutionError):
                rig.writer.run(command)
        assert validate(rig) == (True, None)
