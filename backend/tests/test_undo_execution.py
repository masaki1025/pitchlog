"""実唯一artifactと資格doubleを接合。PG/実E1成功とは主張しない。"""

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from test_nonplay_prefix import rig as rig

from pitchlog.domainrt.host import NodeDomainHost
from pitchlog.repositories import transaction as tx
from pitchlog.sync import undo_execution as api
from pitchlog.sync.undo_execution import UndoExecutionError


@contextmanager
def prepared(rig):
    """source読取/host/評価寿命を保持する。"""
    with api._bind_undo_execution(rig.handle, rig.writer, rig.event, rig.source):
        yield api._EXECUTIONS[rig.handle._state_key]


def test_single_actual_host_full_values_ready_and_close(rig, monkeypatch):
    """単一hostを一回呼び既全5keyを保持する。"""
    calls = []
    original = NodeDomainHost.call

    def call(host, operation, raw):
        calls.append((operation, raw))
        return original(host, operation, raw)

    monkeypatch.setattr(NodeDomainHost, "call", call)
    with prepared(rig) as state:
        assert state.phase == "ready"
        assert state.response.to_wire() == rig.raw["payload"]["calculation"]["response"]
        assert len(calls) == 1 and calls[0][0] == "applyUndo"
        phase = SimpleNamespace(
            kind="content",
            handle=rig.handle,
            bound=rig.source.bound,
            snapshot=rig.source.bound._phase_snapshot,
        )
        with monkeypatch.context() as m:
            m.setattr(tx, "_port_phase", lambda _handle: phase)
            assert api._undo_content_result(rig.handle, rig.event, rig.writer) == (
                True,
                None,
            )
    assert not api._EXECUTIONS


@pytest.mark.parametrize(
    "fault", ["runtime", "top-tx", "writer", "payload", "response", "frame"]
)
def test_frame_lifetime_and_forgery_rejected(rig, monkeypatch, fault):
    """同値clone/失効/全評価値の後発改変を一回消費前に拒否する。"""
    with pytest.raises(RuntimeError):
        with prepared(rig) as state:
            if fault == "runtime":
                monkeypatch.setitem(
                    tx._TRANSACTION_RUNTIMES,
                    rig.handle._state_key,
                    (object(), object()),
                )
            elif fault == "top-tx":
                rig.top.is_active = False
            elif fault == "writer":
                state.writer._close()
            elif fault == "payload":
                state.payload["calculation"]["request"]["current"]["stateFields"][
                    "state.outs"
                ] = "1"
            elif fault == "response":
                object.__setattr__(state.response, "json", "{}")
            else:
                state.frame = object.__new__(api.UndoFrame)
            api._execution_live(state)


def test_real_host_failure_propagates(rig, monkeypatch):
    """host結果不明を内容拒否やFalseへ変換しない。"""

    def fail(*_args):
        raise RuntimeError("fixed host failure")

    monkeypatch.setattr(NodeDomainHost, "call", fail)
    with pytest.raises(RuntimeError, match="fixed host failure"):
        with prepared(rig):
            pytest.fail("host故障が成功しました")


def test_frame_constructor_and_unissued_reference_rejected(rig):
    """自由constructor/未発行参照でSQLへ進めない。"""
    with pytest.raises(UndoExecutionError):
        api.UndoFrame()
    with pytest.raises(UndoExecutionError):
        api._consume_undo_frame(rig.handle, rig.event, rig.writer)


@pytest.mark.parametrize(
    "fault",
    ["nonhead", "stale-cp", "old-target-new-D5", "unknown-control", "forged-result"],
)
def test_content_rejection_is_separate_from_host_or_source_failure(
    rig, monkeypatch, fault
):
    """新D5の不正bodyをstored再送や源本不明へ混同しない。"""
    import copy

    from test_nonplay_prefix import wire_event

    from pitchlog.sync.idempotency import _json_value, event_source
    from pitchlog.sync.wire_fingerprint import freeze_wire_event, wire_event_fingerprint

    raw = copy.deepcopy(rig.raw)
    if fault == "old-target-new-D5":
        from uuid import UUID

        from test_nonplay_prefix import CASES, fixture_values

        rig.value, raw, rig.records = fixture_values(5)
        rig.actual_next_physical = "4"
        raw["d1"], raw["d5"] = 6, str(UUID(int=16006))
        raw["payload"]["calculation"] = copy.deepcopy(
            CASES["undoEvents"][1]["payload"]["calculation"]
        )
        assert raw["target_reference"]["d1"] == 2
        assert rig.value["activeStack"][0]["play"]["source"]["d1"] == "5"
    elif fault == "nonhead":
        raw["target_reference"]["d1"] = 1
    elif fault == "stale-cp":
        raw["payload"]["expectedCheckpoint"]["revision"] = "1"
    elif fault == "unknown-control":
        raw["event_kind"] = "game_reopen"
    else:
        raw["payload"]["calculation"]["response"]["value"]["after"]["stateFields"][
            "state.outs"
        ] = "1"
    rig.event = wire_event(raw)
    rig.source.event = rig.event
    wire = freeze_wire_event(
        json.loads(
            json.dumps(
                _json_value(event_source(rig.event)),
                ensure_ascii=False,
                allow_nan=False,
            )
        )
    )
    rig.view.wire_event, rig.view.event_fingerprint = wire, wire_event_fingerprint(wire)
    with prepared(rig) as state:
        assert state.phase == "rejected" and state.frame is None
        phase = SimpleNamespace(
            kind="content",
            handle=rig.handle,
            bound=rig.source.bound,
            snapshot=rig.source.bound._phase_snapshot,
        )
        with monkeypatch.context() as m:
            m.setattr(tx, "_port_phase", lambda _: phase)
            assert api._undo_content_result(rig.handle, rig.event, rig.writer) == (
                False,
                api._UNDO_CONTENT_REJECTION_REASON,
            )
        assert not any(
            type(op).__name__ in {"_PrepareNonplayUndo", "_ConsumeNonplayUndo"}
            for op in rig.calls
        )


def test_equal_looking_new_transaction_is_not_same_top_tx(rig, monkeypatch):
    """値同値の別TX objectを同一取引へ昇格させない。"""
    with pytest.raises(RuntimeError):
        with prepared(rig) as state:
            monkeypatch.setattr(
                rig.runtime[0],
                "get_transaction",
                lambda: SimpleNamespace(is_active=True),
            )
            api._execution_live(state)


def test_qualification_uses_real_phase_and_expires(rig, monkeypatch):
    """rights専用scope/同bound/snapshotを検査し、自由boolを登録しない。"""
    assert api._undo_qualification_active(rig.handle) is False
    with api._undo_qualification_scope(rig.handle, rig.source):
        assert api._undo_qualification_active(rig.handle) is True
        phase = SimpleNamespace(
            kind="rights",
            handle=rig.handle,
            bound=rig.source.bound,
            snapshot=rig.source.bound._phase_snapshot,
        )
        with monkeypatch.context() as patch:
            patch.setattr(tx, "_port_phase", lambda _: phase)
            assert api._undo_qualification_active(rig.handle) is True
            phase.bound = object()
            with pytest.raises(RuntimeError):
                api._undo_qualification_active(rig.handle)
    assert api._undo_qualification_active(rig.handle) is False


@pytest.mark.parametrize("linked", [True, False])
def test_old_active_generation_is_not_equated_to_own_d4(rig, linked):
    """新世代CPが真正供給されたviewでのみ、旧active対象を取り消せる。"""
    import copy
    from uuid import UUID

    from test_nonplay_prefix import wire_event

    from pitchlog.sync.idempotency import _json_value, event_source, source_fingerprint
    from pitchlog.sync.wire_fingerprint import freeze_wire_event, wire_event_fingerprint

    # 引継ぎ/CP seedの実DB成功ではなく、明示したpoint-read double。
    cp = rig.value["checkpoint"]
    cp["ref"]["id"] = str(UUID(int=6042))
    cp["content"]["scope"]["generation"] = "2"
    cp["content"]["d3"] = "0"
    cp["content"]["d1Head"] = None
    cp["ref"]["digest"] = source_fingerprint(cp["content"])
    raw = copy.deepcopy(rig.raw)
    raw["d4"], raw["d1"] = "2", 1
    raw["payload"]["expectedCheckpoint"] = copy.deepcopy(cp["ref"])
    assert raw["target_reference"]["d4"] == "1"
    rig.raw = raw
    rig.event = wire_event(raw)
    rig.source.event = rig.event
    wire = freeze_wire_event(
        json.loads(
            json.dumps(
                _json_value(event_source(rig.event)),
                ensure_ascii=False,
                allow_nan=False,
            )
        )
    )
    rig.view.wire_event, rig.view.event_fingerprint = wire, wire_event_fingerprint(wire)
    rig.chain = ["1", "2"] if linked else ["2"]
    if linked:
        with prepared(rig) as state:
            assert state.phase == "ready"
            assert (
                state.payload["calculation"]["response"]["value"]["after"][
                    "stateFields"
                ]["state.count.balls"]
                == "1"
            )
    else:
        with pytest.raises(RuntimeError):
            with prepared(rig):
                pytest.fail("非連結世代が成功しました")
