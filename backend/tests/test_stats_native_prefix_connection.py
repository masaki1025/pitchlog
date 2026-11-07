"""prefix実本体のflush接続順だけをDB無しで検査する。

この単体試験の観測用port/bind/flushは認可やDB成功の証拠ではない。
真正資格・同Session・T5・保存は既stats_native_hook/flush各試験と実PGで別検証する。
"""

from __future__ import annotations

import ast
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import cast

import pytest
from test_sync_apply_port_prefix import PrefixProjection, PrefixRights, PrefixValidator
from test_sync_apply_prefix_path import D5, GAME, _AcceptedObservation, _register_ports

from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync import first_ball_execution as first
from pitchlog.sync import native_ledger_insert, ports, prefix_path, stats_native_flush
from pitchlog.sync import ordinary_pitch_execution as ordinary
from pitchlog.sync.first_ball_ports import FirstBallContentValidationPort
from pitchlog.sync.idempotency import D5Candidate, StoredResult
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ordinary_pitch_ports import (
    LineupPrefixContentValidationPort,
    OrdinaryPitchContentValidationPort,
    PlayPrefixContentValidationPort,
)
from pitchlog.sync.ports import _issue_port_writer

_NATIVE = (
    FirstBallContentValidationPort,
    OrdinaryPitchContentValidationPort,
    PlayPrefixContentValidationPort,
    LineupPrefixContentValidationPort,
)


class _FlushFault(RuntimeError):
    """外TXへ伝播させる観測用故障。"""


@pytest.fixture
def rig(monkeypatch):
    """実prefix関数へ観測用DBを渡す。資格検証は成功と主張しない。"""
    trace = []
    scope = _AcceptedObservation()
    writer = _issue_port_writer(scope.run)
    event = SyncEvent(D5, GAME, 1, "epoch", v5="play_input", v6=10, v7={}, v8={})
    _register_ports(monkeypatch)
    # このmoduleは呼出順だけの観測。私有台帳の真正資格は専用試験/実PGで別検証。
    monkeypatch.setattr(
        native_ledger_insert,
        "_recheck_and_insert_native_result",
        lambda handle, actual_writer, original, token, path: (
            prefix_path.recheck_and_insert_result(handle, token, path)
        ),
    )
    monkeypatch.setattr(
        ports,
        "PORT_IMPLEMENTATIONS",
        ports.PORT_IMPLEMENTATIONS
        | frozenset((cls.__module__, cls.__name__) for cls in _NATIVE),
    )
    monkeypatch.setattr(prefix_path, "reach", lambda stage: trace.append(stage))
    monkeypatch.setattr(
        prefix_path, "record_d1_intents", lambda *args: trace.append("intents")
    )

    @contextmanager
    def binding(*args, **kwargs):
        trace.append("execution-open")
        try:
            yield
        finally:
            trace.append("execution-close")

    @contextmanager
    def projection(*args, **kwargs):
        trace.append("projection-open")
        try:
            yield
        finally:
            trace.append("projection-close")

    for module, label in ((first, "first_ball"), (ordinary, "ordinary_pitch")):
        monkeypatch.setattr(module, f"_bind_{label}_execution", binding)
        monkeypatch.setattr(module, f"_bind_{label}_projection", projection)
        completed_name = "first_ball" if module is first else "ordinary"
        monkeypatch.setattr(
            module,
            f"_require_{completed_name}_projection_completed",
            lambda *args: trace.append("completed"),
        )
    for cls in _NATIVE:
        monkeypatch.setattr(cls, "validate", lambda *args: (True, None))

    observed_projection = PrefixProjection()

    def invoke(validator, chosen=None, *, rights=None):
        return prefix_path._apply_locked_in_scope(
            cast(_TenantTransaction, scope),
            event if chosen is None else chosen,
            PrefixRights() if rights is None else rights,
            observed_projection,
            validator,
            None,
            None,
            None,
            source=prefix_path._LEGACY_LOCKED_SOURCE,
            writer=writer,
        )

    yield scope, writer, event, trace, invoke, observed_projection
    writer._close()


@pytest.mark.parametrize("cls", _NATIVE)
def test_native_flush_after_intents_before_execution_cleanup(monkeypatch, rig, cls):
    """4実型だけが元scope/イベント/世代を閉flushへ一度渡す。"""
    scope, writer, event, trace, invoke, observed_projection = rig
    calls = []

    def flush(handle, actual_writer, original, projected, *, generation):
        trace.append("flush")
        calls.append((handle, actual_writer, original, projected, generation))
        assert writer._active is True
        assert trace[-2] == "after_d1_intents"
        assert trace.count("completed") == 1
        assert "execution-close" not in trace

    monkeypatch.setattr(stats_native_flush, "_flush_native_stats", flush)
    result = invoke(cls())
    assert result.accepted and result.d3 == 1
    assert len(calls) == 1
    handle, actual_writer, original, projected, generation = calls[0]
    assert handle is scope and actual_writer is writer and original is event
    assert observed_projection.events == [projected]
    assert observed_projection.events[0] is projected
    assert generation == 1
    assert trace.index("after_t4_projection") < trace.index("intents")
    assert trace.index("intents") < trace.index("after_d1_intents")
    assert trace.index("flush") < trace.index("execution-close")


@pytest.mark.parametrize("cls", _NATIVE)
def test_flush_fault_propagates_to_outer_transaction_and_closes_execution(
    monkeypatch, rig, cls
):
    """flush故障を受理へ変換せず、外TXのrollback位置までそのまま返す。"""
    scope, writer, event, trace, invoke, observed_projection = rig
    fault = _FlushFault("有限故障")

    def flush(*args, **kwargs):
        trace.append("flush-fault")
        raise fault

    monkeypatch.setattr(stats_native_flush, "_flush_native_stats", flush)
    committed = False
    rolled_back = False
    try:
        invoke(cls())
        committed = True
    except _FlushFault as error:
        assert error is fault
        rolled_back = True
    assert not committed and rolled_back
    assert trace[-1] == "execution-close"
    assert trace.count("flush-fault") == 1
    assert writer._active is True  # 呼出者所有writerの寿命をprefixが奪わない。


@pytest.mark.parametrize("cls", _NATIVE)
def test_di2_replay_does_not_issue_new_stats(monkeypatch, rig, cls):
    """既accepted台帳の再掲は新資格発行/新flush/投影へ進まない。"""
    scope, writer, event, trace, invoke, observed_projection = rig
    monkeypatch.setattr(
        prefix_path,
        "classify_d5",
        lambda *args: D5Candidate(
            "stored_result",
            stored=StoredResult(
                "accepted",
                "same",
                {
                    "state": "受理",
                    "d3": 1,
                    "temporary_id_mapping": MappingProxyType({}),
                },
                None,
            ),
        ),
    )
    monkeypatch.setattr(
        stats_native_flush,
        "_flush_native_stats",
        lambda *args, **kwargs: pytest.fail("再掲からflushした"),
    )
    result = invoke(cls())
    assert result.accepted and result.replayed
    assert trace == []


@pytest.mark.parametrize("cls", _NATIVE)
def test_content_rejection_does_not_flush(monkeypatch, rig, cls):
    """内容拒否や未実装を成績保存成功へ変えない。"""
    scope, writer, event, trace, invoke, observed_projection = rig
    monkeypatch.setattr(cls, "validate", lambda *args: (False, "unsupported"))
    monkeypatch.setattr(
        stats_native_flush,
        "_flush_native_stats",
        lambda *args, **kwargs: pytest.fail("拒否からflushした"),
    )
    with pytest.raises(prefix_path.P1ContentRejection):
        invoke(cls())
    assert "after_t4_projection" not in trace
    assert trace[-1] == "execution-close"


def test_non_native_validator_acceptance_does_not_flush(monkeypatch, rig):
    """一般portは受理されてもnative資格の供給対象にしない。"""
    scope, writer, event, trace, invoke, observed_projection = rig
    monkeypatch.setattr(
        stats_native_flush,
        "_flush_native_stats",
        lambda *args, **kwargs: pytest.fail("一般portからflushした"),
    )
    assert invoke(PrefixValidator()).accepted
    assert "after_d1_intents" in trace
    assert "execution-open" not in trace


def test_player_registration_without_required_input_never_flushes(monkeypatch, rig):
    """登録用入力が無い要求をnative成功へ読み替えない。"""
    scope, writer, event, trace, invoke, observed_projection = rig
    monkeypatch.setattr(
        stats_native_flush,
        "_flush_native_stats",
        lambda *args, **kwargs: pytest.fail("登録からflushした"),
    )
    with pytest.raises(prefix_path.P1ContentRejection):
        invoke(PrefixValidator(), replace(event, v5="player_registration"))
    assert "after_t4_projection" not in trace


def test_actual_flush_still_rejects_observation_only_scope(rig):
    """呼出順試験の偽scopeを本物flushの認可資格として使えない。"""
    scope, writer, event, trace, invoke, observed_projection = rig
    with pytest.raises(stats_native_flush.StatsNativeFlushError):
        invoke(FirstBallContentValidationPort())
    assert trace[-1] == "execution-close"


def test_prefix_only_adds_one_closed_flush_without_local_transaction_control():
    """4型exact gate・一callsite・既finallyを静的にも固定する。"""
    source = Path(prefix_path.__file__).read_text()
    module = ast.parse(source)
    fn = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "_apply_locked_in_scope"
    )
    calls = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_flush_native_stats"
    ]
    assert len(calls) == 1
    call = calls[0]
    assert [ast.unparse(node) for node in call.args] == [
        "scope",
        "writer",
        "event",
        "projected_event",
    ]
    assert [(node.arg, ast.unparse(node.value)) for node in call.keywords] == [
        ("generation", "generation")
    ]
    gate = next(
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.If) and any(child is call for child in ast.walk(node))
    )
    assert ast.unparse(gate.test) == (
        "type(validator) in {FirstBallContentValidationPort, "
        "OrdinaryPitchContentValidationPort, "
        "PlayPrefixContentValidationPort, LineupPrefixContentValidationPort}"
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"commit", "rollback"}
        for node in ast.walk(fn)
    )


@pytest.mark.parametrize("cls", _NATIVE)
@pytest.mark.parametrize("stage", ["rights", "gap", "raced-replay"])
def test_prewrite_rejections_and_raced_replay_never_flush(monkeypatch, rig, cls, stage):
    """記録権/連番拒否と台帳競合再掲はflushへ進まず、既後始末を通る。"""
    scope, writer, event, trace, invoke, observed_projection = rig
    monkeypatch.setattr(
        stats_native_flush,
        "_flush_native_stats",
        lambda *args, **kwargs: pytest.fail("拒否/競合再掲からflushした"),
    )
    if stage == "rights":
        monkeypatch.setattr(PrefixRights, "holds_recording_right", lambda *args: False)
        with pytest.raises(prefix_path.P1PreconditionError):
            invoke(cls())
        assert trace == []
    elif stage == "gap":
        result = invoke(cls(), replace(event, d1=2))
        assert result.boundary == "B2" and not result.accepted
        assert trace == []
    else:
        monkeypatch.setattr(
            prefix_path,
            "recheck_and_insert_result",
            lambda *args: D5Candidate(
                "stored_result",
                stored=StoredResult(
                    "accepted",
                    "same",
                    {
                        "state": "受理",
                        "d3": 1,
                        "temporary_id_mapping": MappingProxyType({}),
                    },
                    None,
                ),
            ),
        )
        with pytest.raises(prefix_path._D5Race) as error:
            invoke(cls())
        assert error.value.result.replayed
        assert trace[-1] == "execution-close"
        assert "after_t2_event" not in trace
