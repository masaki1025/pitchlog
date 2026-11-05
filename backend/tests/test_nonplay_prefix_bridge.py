"""一回frame→固定prepare/consume接合。DB応答は明示したdouble。"""

import copy
import json

import pytest
from test_nonplay_prefix import wire_event
from test_stats_native_undo import base_rig as base_rig
from test_stats_native_undo import undo_stats_rig as undo_stats_rig
from test_undo_execution import prepared

from pitchlog.repositories import nonplay_prefix as reader
from pitchlog.sync import nonplay_prefix_bridge as bridge
from pitchlog.sync import undo_execution as execution
from pitchlog.sync.idempotency import _json_value, event_source

rig = undo_stats_rig


@pytest.mark.parametrize(
    "fault", [None, "prepare-exception", "consume-exception", "false", "int", "missing"]
)
def test_one_use_projection_and_fault_propagation(rig, monkeypatch, fault):
    """実frame/全bindを要求し、例外・非bool・不完全応答を成功化しない。"""
    if fault in {"false", "int", "missing"}:
        rig.response_override = {"false": ((False,),), "int": ((1,),), "missing": ()}[
            fault
        ]
    original = rig.handle.run_function.__func__

    def call(handle, token):
        if (
            fault == "prepare-exception" and type(token) is reader._PrepareNonplayUndo
        ) or (
            fault == "consume-exception" and type(token) is reader._ConsumeNonplayUndo
        ):
            # 資格を正常に消費した実SQLの例外を模す。rollback自体のPG証拠ではない。
            reader._qualified_nonplay_call(handle, token)
            raise RuntimeError("fixed SQL failure")
        return original(handle, token)

    monkeypatch.setattr(type(rig.handle), "run_function", call)
    with prepared(rig) as state:
        rig.source.write_started = True
        projected = wire_event(_json_value(event_source(rig.event)))
        if fault is not None:
            with pytest.raises(RuntimeError):
                with execution._bind_undo_projection(
                    rig.handle, rig.writer, rig.event, projected
                ):
                    bridge.project_nonplay_undo(rig.handle, projected, rig.writer)
            with pytest.raises(RuntimeError):
                execution._require_undo_projection_completed(rig.handle, rig.event)
        else:
            with execution._bind_undo_projection(
                rig.handle, rig.writer, rig.event, projected
            ):
                bridge.project_nonplay_undo(rig.handle, projected, rig.writer)
                assert state.phase == "projected"
                with pytest.raises(RuntimeError):
                    bridge.project_nonplay_undo(rig.handle, projected, rig.writer)
            execution._require_undo_projection_completed(rig.handle, rig.event)
            tokens = [
                x
                for x in rig.calls
                if type(x) in {reader._PrepareNonplayUndo, reader._ConsumeNonplayUndo}
            ]
            assert [type(x) for x in tokens] == [
                reader._PrepareNonplayUndo,
                reader._ConsumeNonplayUndo,
            ]
            assert tokens[0].request_json == tokens[1].request_json
            p = json.loads(tokens[0].request_json)
            assert p["after_source"]["checkpoint"]["content"]["d3"] == "3"
            assert p["after_source"]["checkpoint"]["content"]["activeDepth"] == "1"
            assert (
                p["after_source"]["checkpoint"]["content"]["nextPhysicalPlayNumber"]
                == "3"
            )
            assert (
                p["after_source"]["checkpoint"]["content"]["restored"]
                == rig.value["activeStack"][0]["beforeContext"]
            )
            assert p["before_source"] == rig.value
            assert p["after_source"]["activeStack"] == rig.value["activeStack"][1:]
    assert not bridge._WRITE_CALLS


def test_mutated_projected_event_refused_before_sql(rig):
    """projection区間でも元bodyと異なるeventを受理しない。"""
    with prepared(rig):
        rig.source.write_started = True
        raw = copy.deepcopy(rig.raw)
        raw["payload"]["calculation"]["response"]["value"]["after"]["stateFields"][
            "state.outs"
        ] = "1"
        with pytest.raises(RuntimeError):
            with execution._bind_undo_projection(
                rig.handle, rig.writer, rig.event, wire_event(raw)
            ):
                pytest.fail("改変projectionが成功しました")
