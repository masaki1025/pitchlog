"""E1の既認証/device順と取消SQL選択を明示doubleで観測する。"""

import json
from contextlib import contextmanager
from dataclasses import replace
from types import MappingProxyType, SimpleNamespace
from uuid import UUID

import pytest
import test_sync_apply_source_binding as source_test
from test_nonplay_prefix import rig as rig
from test_sync_apply_apply import _e1_private_flow_double

from pitchlog.sync import apply, prefix_path, source_binding, undo_execution
from pitchlog.sync.control_provider import binding_control
from pitchlog.sync.idempotency import D5Candidate, StoredResult
from pitchlog.sync.model import AckResult
from pitchlog.sync.undo_ports import UndoContentValidationPort

_REAL_E1_SOURCE_READ = source_binding._E1CoreSource.read


@pytest.mark.parametrize("d1", [1, 3])
@pytest.mark.parametrize("kind", ["unused", "stored_result", "conflict"])
@pytest.mark.parametrize("format_value", ["native-undo-prefix-v1", "broken"])
def test_d5_internal_classification_precedes_sql_family_but_not_device_return(
    monkeypatch, kind, format_value, d1
):
    """storedの異内容でもhost/CP/frameを先行せず、既device再照合を維持する。"""
    original = source_test._raw

    def raw():
        value = original()
        value["event_kind"] = "undo"
        value["d1"] = d1
        value["payload"] = {"formatVersion": format_value}
        value.pop("d2", None)
        value.pop("state_diff", None)
        return value

    monkeypatch.setattr(source_test, "_raw", raw)
    with _e1_private_flow_double(monkeypatch, "replay") as (
        args,
        kwargs,
        trace,
        _bound,
    ):
        kwargs["validator"] = UndoContentValidationPort()
        phase = replace(kwargs["phase"], d1=d1)
        kwargs["phase"] = phase
        snapshot = json.loads(_bound._phase_snapshot)
        snapshot["phase"] = binding_control._phase_wire(phase, UUID(int=10), 1)
        if d1 != 1:
            snapshot["source_d1"] = d1
        _bound._phase_snapshot = json.dumps(
            snapshot, sort_keys=True, separators=(",", ":")
        )
        _bound._lease._phase_snapshot = _bound._phase_snapshot
        candidate = D5Candidate(
            kind,
            stored=StoredResult(
                "accepted",
                "same",
                {
                    "state": "受理",
                    "d3": d1,
                    "temporary_id_mapping": MappingProxyType({}),
                },
                None,
            )
            if kind == "stored_result"
            else None,
            boundary="B3b" if kind == "conflict" else None,
        )

        def classify(*_args):
            trace.append("internal-d5")
            return (candidate,)

        @contextmanager
        def qualification(scope, source):
            assert source.scope is scope and source.event.v5 == "undo"
            trace.append("undo-sql-open")
            try:
                yield
            finally:
                trace.append("undo-sql-close")

        def preflight(*_args, **_kwargs):
            trace.append("d5-read")
            return apply._BatchPreflight(d1 - 1, (candidate,), True, 1)

        def forbidden(*_args, **_kwargs):
            pytest.fail("stored経路でfresh target/host/frameを取得しました")

        original_kernel = prefix_path._apply_locked_in_scope

        def kernel(*a, **kw):
            if candidate.kind != "unused":
                return prefix_path._candidate_result(candidate, d1 - 1)
            return original_kernel(*a, **kw)

        monkeypatch.setattr(prefix_path, "_apply_locked_in_scope", kernel)
        monkeypatch.setattr(apply, "classify_request_d5", classify)
        monkeypatch.setattr(apply, "_preflight_in_scope", preflight)
        monkeypatch.setattr(undo_execution, "_undo_qualification_scope", qualification)
        monkeypatch.setattr(undo_execution, "_bind_undo_execution", forbidden)
        result = apply._apply_e1_f1(*args, **kwargs)
        assert isinstance(result, AckResult)
        assert trace.index("internal-d5") < trace.index("undo-sql-open")
        assert trace.index("undo-sql-open") < trace.index("device-recheck")
        assert trace.index("device-recheck") < trace.index("d5-read")
        assert trace.index("undo-sql-close") < trace.index("commit")
        assert "mark-written" not in trace
        if kind == "conflict":
            assert result.b3_branch == "B3b"


def test_auth_device_rejection_is_not_replaced_by_stored_ack(monkeypatch):
    """D5の内部分類追加はB5先行を変更しない。"""
    with _e1_private_flow_double(monkeypatch, "replay", device_active=False) as (
        args,
        kwargs,
        trace,
        _bound,
    ):
        kwargs["validator"] = UndoContentValidationPort()
        monkeypatch.setattr(
            apply, "classify_request_d5", lambda *_: pytest.fail("B5より先のD5読取")
        )
        assert apply._apply_e1_f1(*args, **kwargs) == "B5"
        assert "bind" not in trace


@pytest.mark.parametrize("mode", ["DI2", "DI3", "fresh", "exception", "expired"])
def test_real_e1_closes_genuine_undo_qualification_before_active_and_writer_end(
    monkeypatch, rig, mode
):
    """資格/_liveを差替えず、実E1のreturn/失敗でwriter生存中に閉じる。"""
    from pitchlog.repositories import transaction as tx
    from pitchlog.sync.control_provider import writer_binding
    from pitchlog.sync.ports import _issue_port_writer

    original_raw = source_test._raw

    def raw():
        value = original_raw()
        value["event_kind"] = "undo"
        value["payload"] = {"formatVersion": "broken"}
        value.pop("d2", None)
        value.pop("state_diff", None)
        return value

    monkeypatch.setattr(source_test, "_raw", raw)
    # rigはDB/issuerのpure double。genuine read/資格/handle lifetimeを使う。
    monkeypatch.setattr(source_binding._E1CoreSource, "read", _REAL_E1_SOURCE_READ)
    runtime = rig.runtime
    top = rig.top
    with _e1_private_flow_double(monkeypatch, "replay") as (args, kwargs, trace, bound):
        context = args[1]
        key = object()
        monkeypatch.setitem(tx._TRANSACTION_RUNTIMES, key, runtime)
        handle = tx._TenantTransaction(
            context,
            key,
            context.tenant_id,
            context._integrity_proof,
            tx._HANDLE_CREATION_TOKEN,
        )
        old_key = bound._owner[0]
        writer_binding._LIVE_BINDINGS.pop(old_key)
        bound._owner, bound._handle = (key, top), handle
        writer_binding._LIVE_BINDINGS[key] = bound
        kwargs["validator"] = UndoContentValidationPort()
        candidate = (
            D5Candidate("conflict", boundary="B3b")
            if mode == "DI3"
            else (
                D5Candidate(
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
                )
                if mode == "DI2"
                else D5Candidate("unused")
            )
        )
        holder = {}

        @contextmanager
        def tenant_scope(actual_context):
            assert actual_context is context
            trace.append("genuine-tx-open")
            try:
                yield handle
            finally:
                assert tx._SYNC_APPLY_ACTIVE.get() is False
                assert key not in undo_execution._QUALIFICATIONS
                trace.append("genuine-tx-end")

        @contextmanager
        def writer_scope(actual_handle, _rights):
            assert actual_handle is handle
            writer = _issue_port_writer(handle.run)
            gated = SimpleNamespace(writer=writer, written=False)
            holder["writer"] = writer

            def mark():
                gated.written = True

            gated.mark_written = mark
            try:
                yield gated
            finally:
                # 修復前はこの時点で資格が生存し、activeも後でFalseになる。
                assert key not in undo_execution._QUALIFICATIONS
                assert tx._SYNC_APPLY_ACTIVE.get() is True
                assert writer._active is True
                trace.append("genuine-qualification-closed-before-writer")
                writer._close()

        def preflight(*_a, **_kw):
            assert undo_execution._undo_qualification_active(handle) is True
            return apply._BatchPreflight(0, (candidate,), True, 1)

        def event_runner(_handle, event, *_args, **kwargs):
            assert _handle is handle
            assert undo_execution._undo_qualification_active(handle) is True
            if mode == "DI2" or mode == "DI3":
                return prefix_path._candidate_result(candidate, 0)
            kwargs["source"].begin_write(handle, event)
            if mode == "exception":
                raise RuntimeError("event failure")
            if mode == "expired":
                top.is_active = False
            return prefix_path.P1Result(None, 1, True)

        monkeypatch.setattr(apply, "tenant_transaction_scope", tenant_scope)
        monkeypatch.setattr(apply, "gated_e1_writer", writer_scope)
        monkeypatch.setattr(apply, "classify_request_d5", lambda *_: (candidate,))
        monkeypatch.setattr(apply, "_preflight_in_scope", preflight)
        monkeypatch.setattr(prefix_path, "_apply_locked_in_scope", event_runner)
        # genuine qualification/_live/handle/source.readは一切stubにしない。
        token = tx._SYNC_APPLY_ACTIVE.set(False)
        try:
            if mode in {"exception", "expired"}:
                with pytest.raises(RuntimeError):
                    apply._apply_e1_f1(*args, **kwargs)
            else:
                result = apply._apply_e1_f1(*args, **kwargs)
                assert isinstance(result, AckResult)
                assert result.boundary == ("B3" if mode == "DI3" else "B1")
            assert key not in undo_execution._QUALIFICATIONS
            assert holder["writer"]._active is False
            assert trace[-1] == "genuine-tx-end"
        finally:
            top.is_active = True
            tx._SYNC_APPLY_ACTIVE.reset(token)
