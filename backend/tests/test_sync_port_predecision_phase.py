"""Port判定phaseのSQL前拒否を検査する。実PG/認証成功の証拠ではない。"""

from contextlib import ExitStack
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.sql.selectable import Select
from test_authz_tenant_context import make_tenant_context

from pitchlog.repositories import transaction as tx
from pitchlog.repositories.binding import TenantBindingError
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.control_provider import writer_binding
from pitchlog.sync.ports import _issue_port_writer
from pitchlog.sync.tokens import (
    GameReadToken,
    PortBindCurrentDeviceToken,
    PortCheckCurrentRightToken,
    RecordingPrefixUpdateToken,
)


@pytest.fixture
def rig(monkeypatch):
    """real型のhandle+registryとSession doubleでSQL呼出を観測する。"""
    import json

    key = object()
    context = make_tenant_context(UUID(int=1))
    transaction = SimpleNamespace(is_active=True)
    statements = []

    class Session:
        def get_transaction(self):
            return transaction

        def in_nested_transaction(self):
            return False

        def execute(self, statement, params):
            statements.append((statement, params))
            return [] if isinstance(statement, Select) else SimpleNamespace(rowcount=1)

        def begin_nested(self):
            raise AssertionError("判定phaseでsavepointへ到達")

    session = Session()
    runtime = (cast(Any, session), ExitStack())
    monkeypatch.setitem(tx._TRANSACTION_RUNTIMES, key, runtime)
    handle = tx._TenantTransaction(
        context,
        key,
        context.tenant_id,
        context._integrity_proof,
        tx._HANDLE_CREATION_TOKEN,
    )
    bound = object.__new__(writer_binding._LiveWriterBinding)
    bound._handle, bound._used = handle, False
    bound._owner = (key, transaction)
    bound._phase_snapshot = json.dumps(
        {"phase": {"wire_d4": "opaque-d4", "internal_generation": 1}}
    )
    bound._lease = cast(
        Any,
        SimpleNamespace(
            _phase_snapshot=bound._phase_snapshot,
            attempt_id=UUID(int=2),
            phase_id=UUID(int=3),
            nonce=b"n" * 32,
            device_id=UUID(int=4),
            game_id=UUID(int=5),
        ),
    )
    monkeypatch.setitem(writer_binding._LIVE_BINDINGS, key, bound)
    monkeypatch.setattr(
        writer_binding._LiveWriterBinding, "assert_current", lambda self: None
    )
    # 実peer/loan資格でないpure fixture。exact型とassert呼出を別々に検査する。
    from test_sync_apply_writer_binding import _writer

    from pitchlog.recording_rights.rg1_lifecycle import (
        BusinessBinding,
        _Activation,
        _GateLoan,
    )

    loan_calls = []
    loan = object.__new__(_GateLoan)
    bound._identity = _writer()
    loan.binding = BusinessBinding(
        bound._identity.system_identifier,
        int(bound._identity.database_oid),
        "fixture_owned_db",
        bound._identity.postmaster_started_at,
        bound._identity.backend_pid,
    )
    loan._activation = _Activation(UUID(int=91), 1, 902)
    monkeypatch.setitem(tx._RG1_LOANS, key, loan)
    monkeypatch.setattr(
        _GateLoan, "assert_held", lambda actual: loan_calls.append(actual)
    )
    writer = _issue_port_writer(handle.run)
    yield SimpleNamespace(
        handle=handle,
        bound=bound,
        writer=writer,
        statements=statements,
        runtime=runtime,
        loan=loan,
        loan_calls=loan_calls,
    )
    writer._close()
    tx._PORT_PHASES.pop(key, None)
    tx._PORT_DEVICE_BIND_USED.discard(key)


@pytest.mark.parametrize(
    "kind", ("rg1-precheck", "rg1-commit", "device", "rights", "content")
)
def test_every_port_phase_refuses_business_dml_before_sql(rig, kind):
    """判定phaseの有限許可とSQL到達前拒否を確認する。"""
    token = RecordingPrefixUpdateToken(UUID(int=5), 1, 1, 1)
    with tx._port_predecision_phase(rig.handle, kind):
        with pytest.raises(TenantBindingError):
            rig.writer.run(token)
        assert rig.statements == []
    # 制約終了後の核書込は同じrun/同じhandleへ戻る。
    assert rig.handle.run(token).rows == ((1,),)
    assert len(rig.statements) == 1
    assert rig.writer._execute.__self__ is rig.handle
    assert rig.writer._execute.__func__ is tx._TenantTransaction.run


def test_content_read_passes_but_unknown_function_select_does_not(rig, monkeypatch):
    """判定phaseの有限許可とSQL到達前拒否を確認する。"""
    token = GameReadToken(UUID(int=5))
    with tx._port_predecision_phase(rig.handle, "content"):
        assert rig.writer.run(token).rows == ()
        assert len(rig.statements) == 1
        monkeypatch.setattr(
            tx,
            "_prepare_operation",
            lambda *args: (select(func.unknown_side_effect()), {}),
        )
        with pytest.raises(TenantBindingError):
            rig.writer.run(token)
        assert len(rig.statements) == 1


def test_unlisted_read_and_savepoint_are_rejected_before_sql(rig):
    """判定phaseの有限許可とSQL到達前拒否を確認する。"""
    with tx._port_predecision_phase(rig.handle, "rights"):
        with pytest.raises(TenantBindingError):
            rig.writer.run(GameReadToken(UUID(int=5)))
        with pytest.raises(TenantBindingError):
            rig.handle.run_in_savepoint(GameReadToken(UUID(int=5)))
        assert rig.statements == []


def test_phase_cannot_be_transferred_or_nested(rig, monkeypatch):
    """判定phaseの有限許可とSQL到達前拒否を確認する。"""
    with tx._port_predecision_phase(rig.handle, "content"):
        with pytest.raises(TenantBindingError):
            with tx._port_predecision_phase(rig.handle, "content"):
                pytest.fail("nested phase")
        monkeypatch.setitem(
            tx._TRANSACTION_RUNTIMES,
            rig.handle._state_key,
            (rig.runtime[0], ExitStack()),
        )
        with pytest.raises(TenantBindingError):
            rig.writer.run(GameReadToken(UUID(int=5)))
        assert rig.statements == []


def test_function_phase_allowlist_and_nonce_correlation(rig):
    """判定phaseの有限許可とSQL到達前拒否を確認する。"""
    from pitchlog.repositories.writer_binding import _AssertWriterBindingToken

    lease = rig.bound._lease
    with tx._port_predecision_phase(rig.handle, "content"):
        phase = tx._port_phase(rig.handle)
        assert phase is not None
        token = _AssertWriterBindingToken(
            lease.attempt_id,
            lease.phase_id,
            lease.nonce,
            lease.device_id,
            lease.game_id,
        )
        tx._require_port_function(phase, token, "sync_fence_api.assert_writer_binding")
        with pytest.raises(TenantBindingError):
            tx._require_port_function(phase, token, "public.arbitrary_write")
        changed = _AssertWriterBindingToken(
            lease.attempt_id, lease.phase_id, b"x" * 32, lease.device_id, lease.game_id
        )
        with pytest.raises(TenantBindingError):
            tx._require_port_function(
                phase, changed, "sync_fence_api.assert_writer_binding"
            )


def test_finite_bind_fills_private_nonce_and_is_once_per_writer(rig, monkeypatch):
    """判定phaseの有限許可とSQL到達前拒否を確認する。"""
    observed = []

    def fixed_function(self, token):
        observed.append(token)
        return TenantOperationResult(((True,),))

    monkeypatch.setattr(tx._TenantTransaction, "run_function", fixed_function)
    command = PortBindCurrentDeviceToken(b"c" * 32)
    with pytest.raises(TenantBindingError):
        rig.writer.run(command)
    with tx._port_predecision_phase(rig.handle, "device"):
        assert rig.writer.run(command).rows == ((True,),)
        with pytest.raises(TenantBindingError):
            rig.writer.run(command)
    with tx._port_predecision_phase(rig.handle, "device"):
        with pytest.raises(TenantBindingError):
            rig.writer.run(command)
    assert len(observed) == 1
    assert observed[0].binding_nonce == rig.bound._lease.nonce
    assert observed[0].attempt_id == rig.bound._lease.attempt_id
    assert "cccc" not in repr(command)


@pytest.mark.parametrize(
    "field,value",
    (
        ("game_id", UUID(int=90)),
        ("wire_d4", "different"),
        ("recovery_generation", True),
        ("recovery_generation", 0),
        ("proof_digest", b"x" * 31),
    ),
)
def test_finite_right_input_is_bound_and_exact(rig, monkeypatch, field, value):
    """判定phaseの有限許可とSQL到達前拒否を確認する。"""
    from dataclasses import replace

    token = PortCheckCurrentRightToken(UUID(int=5), "opaque-d4", 1, b"p" * 32)
    observed = []
    monkeypatch.setattr(
        tx._TenantTransaction,
        "run_function",
        lambda self, token: observed.append(token),
    )
    with tx._port_predecision_phase(rig.handle, "rights"):
        with pytest.raises(TenantBindingError):
            rig.writer.run(replace(token, **{field: value}))
    assert observed == []


def test_e1_gate_preserves_writer_and_guards_both_rg1_phases(rig, monkeypatch):
    """E1専用gateの③a/⑧が同writer上の別phaseで発火する。"""
    from pitchlog.sync import gate
    from pitchlog.sync.tokens import PortRG1CommitCheckToken, PortRG1PrecheckToken

    seen = []
    calls = []
    monkeypatch.setattr(gate.port_guard, "require_registered_port", lambda port: None)

    def fixed_function(handle, token):
        calls.append(type(token).__name__)
        return TenantOperationResult(((True,),))

    monkeypatch.setattr(tx._TenantTransaction, "run_function", fixed_function)

    class Rights:
        def read_rg1_before_d5(self, writer):
            seen.append(("rg1-precheck", writer))
            phase = tx._port_phase(rig.handle)
            assert phase is not None and phase.kind == "rg1-precheck"
            with pytest.raises(TenantBindingError):
                writer.run(RecordingPrefixUpdateToken(UUID(int=5), 1, 1, 1))
            return writer.run(PortRG1PrecheckToken()).rows[0][0]

        def check_rg1_before_commit(self, writer):
            seen.append(("rg1-commit", writer))
            phase = tx._port_phase(rig.handle)
            assert phase is not None and phase.kind == "rg1-commit"
            return writer.run(PortRG1CommitCheckToken()).rows[0][0]

    with gate.gated_e1_writer(rig.handle, cast(Any, Rights())) as gated:
        assert tx._port_phase(rig.handle) is None
        gated.mark_written()
    assert [kind for kind, _ in seen] == ["rg1-precheck", "rg1-commit"]
    assert seen[0][1] is seen[1][1]
    assert seen[0][1]._execute.__self__ is rig.handle
    assert seen[0][1]._active is False
    assert calls == ["RG1PrecheckToken", "RG1CommitCheckToken"]
    assert rig.statements == []


def test_qualified_presentation_uses_finite_bind_and_rejects_unissued(rig, monkeypatch):
    """私有registry doubleだけの境界試験。実HTTP発行/実資格成功ではない。"""
    import json

    import test_sync_apply_source_binding as source_test

    from pitchlog.sync import source_binding as source

    receipt, request = source_test._receipt_double(source_test._raw())
    owner = source._RECEIPTS[receipt]
    owner.context = rig.handle._context
    owner.tenant_id = rig.handle._context.tenant_id
    rig.bound._lease.game_id = UUID(request.game_id)
    raw = json.loads(rig.bound._phase_snapshot)
    raw["tenant_id"] = str(owner.tenant_id)
    raw["phase"]["request_fingerprint"] = owner.source.request_fingerprint
    rig.bound._phase_snapshot = json.dumps(raw)
    rig.bound._lease._phase_snapshot = rig.bound._phase_snapshot
    for bad in (None, b"digest", object.__new__(writer_binding._DevicePresentation)):
        with pytest.raises(writer_binding.WriterBindingUnavailable):
            writer_binding._recheck_bound_device(rig.bound, bad)
    assert rig.statements == []
    presentation = object.__new__(writer_binding._DevicePresentation)
    state = writer_binding._DevicePresentationState(
        receipt, owner.context, request, rig.bound._lease.device_id, b"c" * 32
    )
    monkeypatch.setitem(writer_binding._DEVICE_PRESENTATIONS, presentation, state)
    owner.device_presentation = presentation
    captured = []

    def run_function(handle, token):
        captured.append(token)
        phase = tx._port_phase(handle)
        assert phase is not None and phase.kind == "device"
        return TenantOperationResult(((True,),))

    monkeypatch.setattr(tx._TenantTransaction, "run_function", run_function)
    assert writer_binding._recheck_bound_device(rig.bound, presentation) is True
    assert len(captured) == 1
    assert captured[0].credential_digest == b"c" * 32
    assert captured[0].binding_nonce == rig.bound._lease.nonce
    assert captured[0].game_id == rig.bound._lease.game_id
    with pytest.raises(TenantBindingError):
        writer_binding._recheck_bound_device(rig.bound, presentation)
    owner.active = False
    with pytest.raises(writer_binding.WriterBindingUnavailable):
        writer_binding._qualified_device_digest(rig.bound, presentation)
    assert len(captured) == 1


@pytest.mark.parametrize("path", ("P1", "P2", "P4"))
@pytest.mark.parametrize("right_matches", (True, False))
@pytest.mark.parametrize("malicious", (True, False))
def test_e1_rejection_guards_malicious_port_and_allows_finite_right(
    rig, monkeypatch, path, right_matches, malicious
):
    """T8/T9共通拒否helperも判定中DML/savepointをSQL0で拒否する。"""
    from pitchlog.sync import rejection, source_binding
    from pitchlog.sync.idempotency import D5Candidate
    from pitchlog.sync.model import SyncEvent

    event = SyncEvent(str(UUID(int=20)), str(UUID(int=5)), 1, "opaque-d4")
    proof = object.__new__(source_binding._E1CoreSource)
    proof.phase = SimpleNamespace(attempt=SimpleNamespace(internal_generation=1))
    monkeypatch.setattr(
        source_binding._E1CoreSource,
        "read",
        lambda self, scope, current: SimpleNamespace(
            event_fingerprint="wire-v1:" + "a" * 64
        ),
    )
    monkeypatch.setattr(rejection, "_lock_game_generation", lambda *args: (1, 0))
    monkeypatch.setattr(rejection, "classify_d5", lambda *args: D5Candidate("unused"))
    monkeypatch.setattr(
        rejection.port_guard, "require_registered_port", lambda port: None
    )
    committed = []

    def commit(*args, **kwargs):
        assert tx._port_phase(rig.handle) is None
        committed.append(kwargs["kind"])
        return kwargs["kind"]

    monkeypatch.setattr(rejection, "_commit_result_in_scope", commit)
    functions = []

    def fixed_function(handle, token):
        phase = tx._port_phase(handle)
        assert phase is not None and phase.kind == "rights"
        functions.append(token)
        return TenantOperationResult(((True, right_matches),))

    monkeypatch.setattr(tx._TenantTransaction, "run_function", fixed_function)

    class Rights:
        def holds_recording_right(self, game_id, d4, v12, writer):
            if malicious:
                for action in (
                    lambda: writer.run(
                        RecordingPrefixUpdateToken(UUID(game_id), 1, 1, 1)
                    ),
                    lambda: rig.handle.run_in_savepoint(GameReadToken(UUID(game_id))),
                ):
                    with pytest.raises(TenantBindingError):
                        action()
            assert rig.statements == []
            value = writer.run(
                PortCheckCurrentRightToken(UUID(game_id), d4, 1, b"p" * 32)
            )
            return value.rows[0][1]

    result = rejection._apply_rejection_in_scope(
        rig.handle,
        event,
        cast(Any, Rights()),
        "proof",
        path,
        None,
        "content rejected",
        "content_rejection",
        rig.writer,
        source=proof,
    )
    expected = "rejected" if right_matches else "evacuated"
    assert result == expected and committed == [expected]
    assert len(functions) == 1
    assert functions[0].binding_nonce == rig.bound._lease.nonce
    assert rig.statements == []
