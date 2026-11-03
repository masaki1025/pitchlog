"""B1実artifact/frameの一回消費。資格/DB/保存の正常成立は含まない。"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from types import MappingProxyType
from typing import Any, cast
from uuid import uuid4

import pytest
from test_sync_apply_first_ball_execution import prepared, validate
from test_sync_apply_first_ball_execution import rig as rig

from pitchlog.repositories import transaction as tx
from pitchlog.sync import first_ball_bridge as bridge
from pitchlog.sync import first_ball_execution as api
from pitchlog.sync.first_ball_frame import FirstBallFrameValue
from pitchlog.sync.ports import _issue_port_writer


def projected(rig, **changes):
    """採番以外は元eventのwire値を保つ。数学を組み立てない。"""
    return replace(rig.event, v6=7, **changes)


def consume(rig, event):
    """実callback区間へ束縛して、既frameだけを消費する。"""
    return api._consume_first_ball_projection(rig.handle, event, rig.writer)


def test_actual_frame_consumed_once_with_original_wire_and_assigned_d2(rig):
    """D2は任意のkernel採番値、frameは原wire指紋のまま同artifact値を返す。"""
    event = projected(rig)
    with prepared(rig):
        # issuer/sourceはpure double。実begin_write境界だけ明示してからB1を呼ぶ。
        assert validate(rig) == (True, None)
        rig.source.begin_write(rig.handle, rig.event)
        state = cast(Any, api._EXECUTIONS[rig.key])
        payload = state.payload
        with api._bind_first_ball_projection(rig.handle, rig.writer, rig.event, event):
            frame = consume(rig, event)
            assert type(frame) is FirstBallFrameValue
            assert frame.source_fingerprint == rig.view.event_fingerprint
            assert frame.d1 == 1 and event.v6 == 7
            assert state.payload is payload and state.phase == "consumed"
            assert bridge._STATES[state.bridge].phase == "consumed"
            with pytest.raises(api.FirstBallExecutionError):
                api._require_first_ball_projection_completed(rig.handle, event)
        assert state.projected_event is state.projection_call is None
        with pytest.raises(RuntimeError):
            consume(rig, event)
    assert not api._EXECUTIONS and not bridge._STATES


@pytest.mark.parametrize(
    "field", ["d5", "game_id", "d1", "d4", "v5", "v7", "v8", "v9", "v10", "v11"]
)
def test_every_non_d2_difference_rejects_before_consume(rig, field, monkeypatch):
    """C2を一括許可せず、原eventの全他fieldを型付きで比較する。"""
    changed = {
        "d5": str(uuid4()),
        "game_id": str(uuid4()),
        "d1": True,
        "d4": "other",
        "v5": 1,
        "v7": {"x": 1},
        "v8": {},
        "v9": None,
        "v10": None,
        "v11": None,
    }
    event = projected(rig, **{field: changed[field]})
    calls = []
    monkeypatch.setattr(
        api, "consume_first_ball_frame", lambda *a, **k: calls.append(True)
    )
    with prepared(rig):
        # issuer/sourceはpure double。実begin_write境界だけ明示してからB1を呼ぶ。
        rig.source.begin_write(rig.handle, rig.event)
        with pytest.raises(api.FirstBallExecutionError):
            with api._bind_first_ball_projection(
                rig.handle, rig.writer, rig.event, event
            ):
                pytest.fail("不正投影がcallbackへ到達")
        assert not calls
        with pytest.raises(RuntimeError):
            with api._bind_first_ball_projection(
                rig.handle, rig.writer, rig.event, projected(rig)
            ):
                pytest.fail("失敗後のframe再貸与")


@pytest.mark.parametrize("value", [True, -1, "7", None, 2**63])
def test_invalid_assigned_d2_is_not_coerced(rig, value):
    """採番値はexact非負bigintだけ。bool/範囲外を丸めない。"""
    event = replace(rig.event, v6=value)
    with prepared(rig):
        # issuer/sourceはpure double。実begin_write境界だけ明示してからB1を呼ぶ。
        rig.source.begin_write(rig.handle, rig.event)
        with pytest.raises(api.FirstBallExecutionError):
            with api._bind_first_ball_projection(
                rig.handle, rig.writer, rig.event, event
            ):
                pytest.fail("不正D2が採用された")


def test_mapping_implementation_difference_allowed_but_nested_bool_is_not_int(rig):
    """Mappingの具象型差は許すが、等値に見える葉のwire型は区別する。"""
    assert api._same_wire_value(MappingProxyType({"a": (1,)}), {"a": (1,)})
    assert not api._same_wire_value({"a": True}, {"a": 1})
    assert not api._same_wire_value({"a": (1,)}, {"a": (True,)})
    assert not api._same_wire_value({"a": (1,)}, {"a": [1]})
    with prepared(rig):
        # issuer/sourceはpure double。実begin_write境界だけ明示してからB1を呼ぶ。
        rig.source.begin_write(rig.handle, rig.event)
        event = projected(rig)
        object.__setattr__(event, "v7", dict(rig.event.v7))
        with api._bind_first_ball_projection(rig.handle, rig.writer, rig.event, event):
            assert consume(rig, event).source_fingerprint == rig.view.event_fingerprint


@pytest.mark.parametrize(
    "kind", ["clone", "writer", "nonce", "phase", "source", "d2", "payload", "double"]
)
def test_callback_identity_live_source_and_mutated_projected_are_rechecked(rig, kind):
    """元参照・nonce・source・phaseと採番値を消費時にも再検査する。"""
    event = projected(rig)
    with prepared(rig):
        # issuer/sourceはpure double。実begin_write境界だけ明示してからB1を呼ぶ。
        rig.source.begin_write(rig.handle, rig.event)
        expected_exit = (
            pytest.raises(RuntimeError)
            if kind in ("nonce", "phase", "source")
            else nullcontext()
        )
        with expected_exit:
            with api._bind_first_ball_projection(
                rig.handle, rig.writer, rig.event, event
            ):
                other = None
                if kind == "clone":
                    event = replace(event)
                elif kind == "writer":
                    other = _issue_port_writer(rig.handle.run)
                elif kind == "nonce":
                    rig.bound._lease.nonce = b"x" * 32
                elif kind == "phase":
                    rig.source.phase = object()
                elif kind == "source":
                    rig.source.event = replace(rig.event)
                elif kind == "d2":
                    object.__setattr__(event, "v6", 8)
                elif kind == "payload":
                    object.__setattr__(event, "v7", {})
                elif kind == "double":
                    consume(rig, event)
                try:
                    with pytest.raises(RuntimeError):
                        api._consume_first_ball_projection(
                            rig.handle, event, other or rig.writer
                        )
                    with pytest.raises(RuntimeError):
                        consume(rig, projected(rig))
                finally:
                    if other is not None:
                        other._close()
    assert not api._EXECUTIONS and not bridge._STATES


def test_outside_callback_clone_original_nested_and_expired_rejected(rig):
    """同値原event・nested・失効を別の資格入口にしない。"""
    event = projected(rig)
    with prepared(rig):
        # issuer/sourceはpure double。実begin_write境界だけ明示してからB1を呼ぶ。
        rig.source.begin_write(rig.handle, rig.event)
        with pytest.raises(RuntimeError):
            with api._bind_first_ball_projection(
                rig.handle, rig.writer, replace(rig.event), event
            ):
                pytest.fail("同値原event許可")
    with pytest.raises(RuntimeError):
        consume(rig, event)


@pytest.mark.parametrize("assigned_d2", [0, 7, 2**63 - 1])
def test_b2_absent_still_rolls_back_after_kernel_callback(
    rig, monkeypatch, assigned_d2
):
    """実prefix O4後callbackで一回consumeしても、B2未提供なら成功へ進めない。"""
    from pitchlog.repositories.tokens import TenantOperationResult
    from pitchlog.sync import prefix_path
    from pitchlog.sync.first_ball_ports import FirstBallContentValidationPort
    from pitchlog.sync.idempotency import D5Candidate
    from pitchlog.sync.tokens import (
        EventSlotInsertToken,
        OperationEventInsertToken,
        RecordingPrefixUpdateToken,
    )

    original = tx._TenantTransaction.run
    writes, consumed, opened = [], [], []

    def run(handle, operation):
        if type(operation) in (
            EventSlotInsertToken,
            OperationEventInsertToken,
            RecordingPrefixUpdateToken,
        ):
            writes.append(type(operation).__name__)
            return TenantOperationResult(((1,),))
        return original(handle, operation)

    monkeypatch.setattr(tx._TenantTransaction, "run", run)
    rig.writer._close()
    rig.writer = _issue_port_writer(rig.handle.run)
    monkeypatch.setattr(prefix_path, "_lock_game_generation", lambda *a: (1, 0))
    monkeypatch.setattr(prefix_path, "classify_d5", lambda *a: D5Candidate("unused"))
    monkeypatch.setattr(prefix_path, "recheck_and_insert_result", lambda *a: None)
    monkeypatch.setattr(
        prefix_path.port_guard, "require_registered_port", lambda _: None
    )
    actual = bridge.open_domain_host

    def host():
        opened.append(True)
        return actual()

    monkeypatch.setattr(bridge, "open_domain_host", host)

    class Rights:
        def holds_recording_right(self, *args):
            return True

    class Projection:
        def apply(self, event, writer):
            assert event is not rig.event and event.v6 == assigned_d2
            frame = api._consume_first_ball_projection(rig.handle, event, writer)
            consumed.append(frame)

    with tx._sync_apply_active():
        with pytest.raises(api.FirstBallExecutionError):
            prefix_path._apply_locked_in_scope(
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
                order_resolver=lambda *a: assigned_d2,
                writer=rig.writer,
            )
    assert len(consumed) == 1 and opened == [True]
    assert writes == [
        "EventSlotInsertToken",
        "OperationEventInsertToken",
        "RecordingPrefixUpdateToken",
    ]
    assert not api._EXECUTIONS and not bridge._STATES


def test_nested_projection_and_wrong_phase_never_issue_another_frame(rig):
    """呼出区間の再入や判定phaseをprojection資格へ広げない。"""
    event = projected(rig)
    with prepared(rig):
        # issuer/sourceはpure double。実begin_write境界だけ明示してからB1を呼ぶ。
        rig.source.begin_write(rig.handle, rig.event)
        with api._bind_first_ball_projection(rig.handle, rig.writer, rig.event, event):
            with pytest.raises(RuntimeError):
                with api._bind_first_ball_projection(
                    rig.handle, rig.writer, rig.event, event
                ):
                    pytest.fail("nested")
            with pytest.raises(RuntimeError):
                consume(rig, event)


def test_predecision_phase_never_becomes_projection_authority(rig):
    """判定readのDML禁止phaseへ投影許可を追加しない。"""
    event = projected(rig)
    with prepared(rig):
        # issuer/sourceはpure double。実begin_write境界だけ明示してからB1を呼ぶ。
        rig.source.begin_write(rig.handle, rig.event)
        with tx._port_predecision_phase(rig.handle, "content"):
            with pytest.raises(RuntimeError):
                with api._bind_first_ball_projection(
                    rig.handle, rig.writer, rig.event, event
                ):
                    pytest.fail("判定phaseで投影")


def test_before_e1_begin_write_cannot_open_projection(rig):
    """readyでもO4前/書込前は投影資格を発行しない。"""
    with prepared(rig):
        assert rig.source.write_started is False
        with pytest.raises(api.FirstBallExecutionError):
            with api._bind_first_ball_projection(
                rig.handle, rig.writer, rig.event, projected(rig)
            ):
                pytest.fail("書込前に投影成功")


def test_handle_expiry_inside_callback_closes_frame(rig):
    """実handle失効後に同値参照でframeを借り直さない。"""
    event = projected(rig)
    with prepared(rig):
        rig.source.begin_write(rig.handle, rig.event)
        with pytest.raises(RuntimeError):
            with api._bind_first_ball_projection(
                rig.handle, rig.writer, rig.event, event
            ):
                rig.handle._expire()
                with pytest.raises(RuntimeError):
                    consume(rig, event)
        with pytest.raises(RuntimeError):
            consume(rig, event)
    assert not api._EXECUTIONS and not bridge._STATES


def test_callback_fault_after_consume_never_reopens_frame(rig):
    """callback途中故障を保存完了へ変えず、そのframeは再利用しない。"""
    event = projected(rig)
    with prepared(rig):
        rig.source.begin_write(rig.handle, rig.event)
        with pytest.raises(RuntimeError, match="public planned fault"):
            with api._bind_first_ball_projection(
                rig.handle, rig.writer, rig.event, event
            ):
                consume(rig, event)
                raise RuntimeError("public planned fault")
        with pytest.raises(RuntimeError):
            consume(rig, event)
        with pytest.raises(RuntimeError):
            api._require_first_ball_projection_completed(rig.handle, event)


@pytest.mark.parametrize("d2", [0, 2**53, 2**63 - 1])
def test_assigned_d2_full_ordering_bigint_boundaries(rig, d2):
    """既orderingの0/JS安全整数超/PG bigint上限を損失なく保持する。"""
    event = replace(rig.event, v6=d2)
    with prepared(rig):
        rig.source.begin_write(rig.handle, rig.event)
        with api._bind_first_ball_projection(rig.handle, rig.writer, rig.event, event):
            frame = consume(rig, event)
            assert event.v6 == d2 and type(event.v6) is int
            assert frame.source_fingerprint == rig.view.event_fingerprint
            with pytest.raises(api.FirstBallExecutionError):
                api._require_first_ball_projection_completed(rig.handle, event)
