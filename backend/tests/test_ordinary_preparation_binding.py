"""prepareのtokenidentity/全値変更/一回性。実writer資格の証明とは別。"""

from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest

from pitchlog.repositories.ordinary_pitch_qualification import (
    PrepareOrdinaryProjectionToken,
)
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync import ordinary_pitch_execution as execution


def _setup(monkeypatch):
    """実scope型の比較を残し、生存確認だけを本単体境界の外へ分離する。"""
    handle = object.__new__(_TenantTransaction)
    object.__setattr__(handle, "_state_key", object())
    lease = SimpleNamespace(
        attempt_id=UUID(int=1),
        phase_id=UUID(int=2),
        nonce=b"a" * 32,
        device_id=UUID(int=3),
    )
    state = execution._Execution(
        handle,
        None,
        SimpleNamespace(bound=SimpleNamespace(_lease=lease)),
        SimpleNamespace(game_id=str(UUID(int=4))),
        None,
        None,
    )
    state.phase = "consumed"
    state.projection_call = object()
    token = PrepareOrdinaryProjectionToken(
        lease.attempt_id,
        lease.phase_id,
        lease.nonce,
        lease.device_id,
        UUID(int=4),
        "{}",
    )
    monkeypatch.setitem(execution._EXECUTIONS, handle._state_key, state)
    monkeypatch.setattr(execution, "_live", lambda state: None)
    return handle, state, token


def test_unbound_free_token_and_before_frame_are_rejected(monkeypatch):
    """自由dataclassだけではprepare消費へ到達しない。"""
    handle, state, token = _setup(monkeypatch)
    with pytest.raises(execution.OrdinaryPitchExecutionError):
        execution._consume_ordinary_preparation(handle, token)
    state.phase = "ready"
    with (
        pytest.raises(execution.OrdinaryPitchExecutionError),
        execution._bind_ordinary_preparation(state, token),
    ):
        pytest.fail("prepare区間を開けない")


def test_only_identical_token_once_and_unchanged_payload(monkeypatch):
    """等値別instance、raw変更、二度目をSQL前の消費で拒否する。"""
    handle, state, token = _setup(monkeypatch)
    with execution._bind_ordinary_preparation(state, token):
        with pytest.raises(execution.OrdinaryPitchExecutionError):
            execution._consume_ordinary_preparation(handle, replace(token))
        object.__setattr__(token, "preparation_json", '{"x":1}')
        with pytest.raises(execution.OrdinaryPitchExecutionError):
            execution._consume_ordinary_preparation(handle, token)
        object.__setattr__(token, "preparation_json", "{}")
        execution._consume_ordinary_preparation(handle, token)
        with pytest.raises(execution.OrdinaryPitchExecutionError):
            execution._consume_ordinary_preparation(handle, token)
    assert state.preparation_token is None and state.preparation_digest is None


def test_cross_scope_and_writer_identity_are_rejected(monkeypatch):
    """別handle/別writer参照へtokenを貸さない。"""
    handle, state, token = _setup(monkeypatch)
    with (
        pytest.raises(execution.OrdinaryPitchExecutionError),
        execution._bind_ordinary_preparation(
            state, replace(token, device_id=UUID(int=8))
        ),
    ):
        pytest.fail("別deviceを許さない")
    with execution._bind_ordinary_preparation(state, token):
        other = object.__new__(_TenantTransaction)
        object.__setattr__(other, "_state_key", object())
        with pytest.raises(execution.OrdinaryPitchExecutionError):
            execution._consume_ordinary_preparation(other, token)
        execution._consume_ordinary_preparation(handle, token)


def test_direct_registered_prepare_without_actual_frame_executes_zero_sql(monkeypatch):
    """run_function実物が自由prepare tokenをSession到達前に拒否する。"""
    from test_authz_tenant_context import make_tenant_context

    from pitchlog.repositories import transaction

    class NoExecute:
        """SQL到達を許さない合成Session。実DBの代替成功は返さない。"""

        def execute(self, statement, parameters):
            """ここへ到達したら対向失敗。"""
            raise AssertionError("自由prepareがSQLへ到達")

    tenant = UUID(int=10)
    context = make_tenant_context(tenant)
    key = object()
    monkeypatch.setitem(transaction._TRANSACTION_RUNTIMES, key, (NoExecute(), object()))
    handle = _TenantTransaction(
        context,
        key,
        tenant,
        context._integrity_proof,
        transaction._HANDLE_CREATION_TOKEN,
    )
    token = PrepareOrdinaryProjectionToken(
        UUID(int=1), UUID(int=2), b"a" * 32, UUID(int=3), UUID(int=4), "{}"
    )
    with pytest.raises(execution.OrdinaryPitchExecutionError):
        handle.run_function(token)
