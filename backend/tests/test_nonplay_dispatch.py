"""実Source17→新固定SQLと実undo Port dispatcherの接合対向。"""

from uuid import UUID

import pytest
from test_nonplay_qualification import decision_phase
from test_nonplay_qualification import function_rig as function_rig
from test_nonplay_qualification import rig as rig
from test_undo_execution import prepared

from pitchlog.repositories import nonplay_prefix as reader
from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    prepare_function_operation,
)
from pitchlog.repositories.operation_registry import FUNCTION_OPERATION_REGISTRY
from pitchlog.sync import undo_execution as execution
from pitchlog.sync.tokens import PortBindCurrentDeviceToken, PortCheckCurrentRightToken
from pitchlog.sync.undo_ports import (
    UndoContentValidationPort,
    UndoProjectionPort,
    ValidateUndoToken,
)


def test_real_prefix_getter_consumes_private_qualification_before_fixed_sql(
    function_rig,
):
    """同実reader/一回getter/正準registryを通して有限pageを読み戻す。"""
    r = function_rig
    with reader.read_confirmed_nonplay_prefix(
        r.handle, r.event, r.source, artifact_sha256=r.raw["payload"]["artifactSha256"]
    ) as prefix:
        value, _ = reader._read_prefix(prefix, r.handle, r.source, r.event)
        assert value == r.value
    assert [x[0] for x in r.sql] == [
        "lock_nonplay_checkpoint",
        "read_nonplay_history_page",
        "read_nonplay_history_page",
    ]
    assert all(x[1]["binding_nonce"] == r.lease.nonce for x in r.sql)


def test_private_source17_token_has_no_generic_or_unissued_sql_path(function_rig):
    """actual型も単独では未登録で、閉mappingだけでは資格を作らない。"""
    r = function_rig
    token = reader._LockNonplayCheckpoint("{}")
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(
            token, r.handle._bound_tenant_id, FUNCTION_OPERATION_REGISTRY
        )
    with pytest.raises(RuntimeError):
        r.handle.run_function(token)
    assert not r.sql


@pytest.mark.parametrize("fault", ["sql", "text-int", "empty-lock", "extra-row"])
def test_private_sql_errors_and_row_corruption_propagate(function_rig, fault):
    """SQL不可用やdriver型/件数を空正常へ修復しない。"""
    r = function_rig
    if fault == "sql":
        r.sql_fault = RuntimeError("missing formal SQL profile")
    else:
        r.sql_rows = {
            "text-int": ((1,),),
            "empty-lock": (),
            "extra-row": (("{}",), ("{}",)),
        }[fault]
    with pytest.raises(RuntimeError):
        with reader.read_confirmed_nonplay_prefix(
            r.handle,
            r.event,
            r.source,
            artifact_sha256=r.raw["payload"]["artifactSha256"],
        ):
            pytest.fail("破損した固定SQLを成功にしました")


def test_actual_undo_host_content_then_bridge_uses_fixed_prepare_consume(
    function_rig, monkeypatch
):
    """実host一回/実hook tuple/実Port/実bridge/固定SQL2へ一回到達する。"""
    r = function_rig
    with prepared(r):
        with decision_phase(r, monkeypatch, "content"):
            assert UndoContentValidationPort().validate(r.event, r.writer) == (
                True,
                None,
            )
            forged = ValidateUndoToken(UUID(int=9), UUID(r.event.d5), r.event, r.writer)
            with pytest.raises(RuntimeError):
                r.handle.run(forged)
        r.source.write_started = True
        # 元DTOと同値の別projected実体も、既projection区間でのみ使う。
        from test_nonplay_prefix import wire_event

        from pitchlog.sync.idempotency import _json_value, event_source

        projected = wire_event(_json_value(event_source(r.event)))
        with execution._bind_undo_projection(r.handle, r.writer, r.event, projected):
            UndoProjectionPort().apply(projected, r.writer)
        execution._require_undo_projection_completed(r.handle, r.event)
    assert [name for name, _ in r.sql][-2:] == [
        "prepare_nonplay_undo",
        "consume_nonplay_undo",
    ]
    assert r.sql[-1][1]["request_json"] == r.sql[-2][1]["request_json"]


@pytest.mark.parametrize("kind", ["device", "rights"])
def test_real_port_commands_choose_nonplay_only_for_issued_source(
    function_rig, monkeypatch, kind
):
    """stored再掲でも使う既deviceを保持し、fresh host/targetを要求しない。"""
    r = function_rig
    with execution._undo_qualification_scope(r.handle, r.source):
        with decision_phase(r, monkeypatch, kind):
            command = (
                PortBindCurrentDeviceToken(b"c" * 32)
                if kind == "device"
                else PortCheckCurrentRightToken(r.lease.game_id, "1", 3, b"p" * 32)
            )
            result = r.handle.run(command)
            assert result.rows == (((True,),) if kind == "device" else ((True, True),))
    assert len(r.sql) == 1
    assert r.sql[0][0] == (
        "bind_nonplay_device" if kind == "device" else "check_nonplay_right"
    )


def test_unknown_undo_command_subtype_and_no_phase_do_not_reach_sql(function_rig):
    """Actual exact型/phaseを持たない命令を一般DMLやSQLへ昇格しない。"""
    r = function_rig
    with pytest.raises(RuntimeError):
        UndoContentValidationPort().validate(r.event, r.writer)

    class Derived(ValidateUndoToken):
        """同値の派生命令は実登録型ではない。"""

    with pytest.raises(RuntimeError):
        r.handle.run(Derived(r.lease.game_id, UUID(r.event.d5), r.event, r.writer))
    assert not r.sql


def test_actual_private_call_consumes_once_and_rejects_mutated_original(function_rig):
    """実Source17 loanがSQL前に一回消費され、同token再使用を拒否する。"""
    r = function_rig
    token = reader._LockNonplayCheckpoint("{}")
    with reader._call_scope(r.handle, r.source, r.event, token):
        assert r.handle.run_function(token).rows
        with pytest.raises(RuntimeError):
            r.handle.run_function(token)
    assert len(r.sql) == 1
    token = reader._LockNonplayCheckpoint("{}")
    with pytest.raises(RuntimeError):
        with reader._call_scope(r.handle, r.source, r.event, token):
            object.__setattr__(token, "request_json", '{"changed":true}')
            r.handle.run_function(token)
    assert len(r.sql) == 1


def test_actual_private_call_rechecks_source_after_sql(function_rig, monkeypatch):
    """既call_scopeの終了source確認を省略せず、失効結果を返さない。"""
    from pitchlog.sync.source_binding import _E1CoreSource

    r = function_rig
    original = _E1CoreSource.read

    def read(source, handle, event):
        if r.sql:
            raise RuntimeError("expired actual source after SQL")
        return original(source, handle, event)

    monkeypatch.setattr(_E1CoreSource, "read", read)
    with pytest.raises(RuntimeError, match="expired actual source after SQL"):
        reader._run(r.handle, r.source, r.event, reader._LockNonplayCheckpoint("{}"))
    assert len(r.sql) == 1


def test_equal_looking_qualified_result_is_not_actual_getter_type(
    function_rig, monkeypatch
):
    """getter戻りの同値cloneを真のQualifiedNonplayCallへ昇格しない。"""
    from types import MappingProxyType, SimpleNamespace

    r = function_rig
    token = reader._LockNonplayCheckpoint("{}")
    fake = SimpleNamespace(
        operation=token,
        function_name="lock_nonplay_checkpoint",
        parameters=MappingProxyType(
            {
                "tenant_id": r.handle._bound_tenant_id,
                "attempt_id": r.lease.attempt_id,
                "phase_id": r.lease.phase_id,
                "binding_nonce": r.lease.nonce,
                "device_id": r.lease.device_id,
                "game_id": r.lease.game_id,
                "request_json": "{}",
            }
        ),
    )
    monkeypatch.setattr(reader, "_qualified_nonplay_call", lambda _h, _o: fake)
    with pytest.raises(FunctionOperationError):
        r.handle.run_function(token)
    assert not r.sql
