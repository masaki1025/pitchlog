"""既P1核の取消接合を明示doubleで検査する。PG/資格の実証ではない。"""

from contextlib import contextmanager
from types import MappingProxyType, SimpleNamespace
from typing import cast
from uuid import UUID

import pytest
from test_sync_apply_port_prefix import PrefixRights
from test_sync_apply_prefix_path import D5, GAME, _AcceptedObservation

from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync import native_ledger_insert, ports, prefix_path, stats_native_flush
from pitchlog.sync import undo_execution as undo
from pitchlog.sync.idempotency import D5Candidate, StoredResult
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.tokens import OperationEventInsertToken
from pitchlog.sync.undo_ports import (
    ProjectUndoToken,
    UndoContentValidationPort,
    UndoProjectionPort,
    ValidateUndoToken,
)


def event(*, own="2", target="1", d1=1):
    """native版でown世代とtarget世代を明示する。"""
    return SyncEvent(
        D5,
        GAME,
        d1,
        own,
        v5="undo",
        v7={"formatVersion": "native-undo-prefix-v1"},
        v10={"game": GAME, "d4": target, "d1": 2},
    )


@pytest.mark.parametrize("own,target", [("2", "1"), ("1", "1")])
def test_native_target_generation_is_v10_not_own_generation(own, target, monkeypatch):
    """真正readerは別途必要だが核は解決済みtargetの世代を保持する。"""
    e = event(own=own, target=target)
    reserved = UUID(int=91)
    monkeypatch.setattr(undo, "_reserved_undo_event_id", lambda h, x: reserved)
    result = prefix_path._event_insert_token(
        e,
        UUID(GAME),
        int(own),
        "none",
        "{}",
        prefix_path.P1Target(UUID(GAME), int(target), 2),
        scope=object(),
    )
    assert result.id == reserved
    assert result.target_generation == int(target)
    assert result.generation == int(own)
    assert result.d2 is None and result.state_diff_json is None


@pytest.mark.parametrize("target", [2, 0, -1, True])
def test_wrong_or_nonpositive_target_rejected(target):
    """own世代への誤置換やbool/int混同を許さない。"""
    with pytest.raises(prefix_path.P1PreconditionError, match="V10"):
        prefix_path._validate_v10(
            event(), "none", prefix_path.P1Target(UUID(GAME), target, 2)
        )


class Scope(_AcceptedObservation):
    """tokenの順序だけを観測し保存/認可を成立扱いにしない。"""

    def __init__(self, trace, *, valid=True, projection_fault=False):
        """空の観測と明示doubleの応答を持つ。"""
        super().__init__()
        self.trace, self.valid, self.projection_fault = trace, valid, projection_fault

    def run(self, token):
        """Port命令の既応答形だけを模擬する。"""
        if type(token) is ValidateUndoToken:
            self.trace.append("content")
            return TenantOperationResult(
                (
                    (
                        self.valid,
                        None
                        if self.valid
                        else "取消内容が確定原本または実評価値と不一致",
                    ),
                )
            )
        if type(token) is ProjectUndoToken:
            self.trace.append("projection")
            if self.projection_fault:
                raise RuntimeError("projection failure")
            return TenantOperationResult(((True,),))
        if type(token) is OperationEventInsertToken:
            self.trace.append("event")
        return super().run(token)


@pytest.fixture
def kernel(monkeypatch):
    """実kernelと実Portを呼び、評価/DB境界だけを明示doubleにする。"""
    trace = []
    scope = Scope(trace)
    e = event()
    monkeypatch.setattr(prefix_path, "_lock_game_generation", lambda *_: (2, 0))
    monkeypatch.setattr(
        prefix_path, "record_d1_intents", lambda *_: trace.append("intent")
    )
    monkeypatch.setattr(prefix_path, "classify_d5", lambda *_: D5Candidate("unused"))
    monkeypatch.setattr(
        ports,
        "PORT_IMPLEMENTATIONS",
        frozenset(
            (c.__module__, c.__name__)
            for c in [PrefixRights, UndoContentValidationPort, UndoProjectionPort]
        ),
    )

    @contextmanager
    def execution(*_):
        trace.append("frame-open")
        try:
            yield
        finally:
            trace.append("frame-close")

    @contextmanager
    def projection(*_):
        trace.append("projection-open")
        try:
            yield
        finally:
            trace.append("projection-close")

    monkeypatch.setattr(undo, "_bind_undo_execution", execution)
    monkeypatch.setattr(undo, "_bind_undo_projection", projection)
    monkeypatch.setattr(
        undo, "_require_undo_projection_completed", lambda *_: trace.append("completed")
    )
    monkeypatch.setattr(undo, "_reserved_undo_event_id", lambda *_: UUID(int=91))
    monkeypatch.setattr(
        native_ledger_insert,
        "_recheck_and_insert_native_result",
        lambda *_: trace.append("native-ledger"),
    )

    def run():
        return prefix_path._apply_locked(
            cast(_TenantTransaction, scope),
            e,
            PrefixRights(),
            UndoProjectionPort(),
            UndoContentValidationPort(),
            None,
            None,
            prefix_path.P1Target(UUID(GAME), 1, 2),
        )

    return SimpleNamespace(trace=trace, scope=scope, run=run, event=e)


def test_real_kernel_order_projection_completion_and_distinct_s_hook(
    kernel, monkeypatch
):
    """Sは明示doubleであり、play StatsStateを取消へ流さない。"""
    monkeypatch.setattr(
        stats_native_flush,
        "_flush_native_undo_stats",
        lambda *_args, **_kw: kernel.trace.append("undo-S"),
        raising=False,
    )
    result = kernel.run()
    assert result.accepted and result.d3 == 1
    assert kernel.trace == [
        "frame-open",
        "content",
        "native-ledger",
        "event",
        "projection-open",
        "projection",
        "projection-close",
        "completed",
        "intent",
        "undo-S",
        "frame-close",
    ]
    assert len(kernel.scope.events) == 1 and kernel.scope.events[0].id == UUID(int=91)


def test_missing_s_hook_is_not_success(kernel, monkeypatch):
    """root未供給hookは最後まで実経路を通しても成功へ補完しない。"""
    monkeypatch.delattr(stats_native_flush, "_flush_native_undo_stats", raising=False)
    with pytest.raises(undo.UndoExecutionError, match="canonical S hook"):
        kernel.run()
    assert kernel.trace[-1] == "frame-close"


@pytest.mark.parametrize("fault", ["content", "projection", "completion", "S"])
def test_faults_propagate_and_frame_scope_closes(kernel, monkeypatch, fault):
    """同TX rollbackは外側の責務であり、kernelで握り潰さない。"""

    def fail(*_a, **_k):
        raise RuntimeError("injected failure")

    if fault == "content":
        kernel.scope.valid = False
    elif fault == "projection":
        kernel.scope.projection_fault = True
    elif fault == "completion":
        monkeypatch.setattr(undo, "_require_undo_projection_completed", fail)
    else:
        monkeypatch.setattr(
            stats_native_flush, "_flush_native_undo_stats", fail, raising=False
        )
    with pytest.raises((RuntimeError, prefix_path.P1ContentRejection)):
        kernel.run()
    assert kernel.trace[-1] == "frame-close"
    if fault == "content":
        assert not kernel.scope.events and "native-ledger" not in kernel.trace


@pytest.mark.parametrize("stored_kind", ["accepted", "rejected", "evacuated"])
def test_stored_d5_precedes_new_frame_content_and_ports(
    kernel, monkeypatch, stored_kind
):
    """再掲時にfresh hook/内容/投影/新Sを要求しない。"""
    monkeypatch.setattr(
        prefix_path,
        "classify_d5",
        lambda *_: D5Candidate(
            "stored_result",
            stored=StoredResult(
                stored_kind,
                "same",
                {
                    "state": {
                        "accepted": "受理",
                        "rejected": "拒否",
                        "evacuated": "退避",
                    }[stored_kind],
                    "d3": 1,
                    "temporary_id_mapping": MappingProxyType({}),
                },
                "stored rejection" if stored_kind == "rejected" else None,
            ),
        ),
    )
    result = kernel.run()
    assert result.replayed and not kernel.trace and not kernel.scope.events
