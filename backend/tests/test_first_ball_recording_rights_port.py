"""初球P2実Portと核のpure境界。実DB/実loan発行とは区別する。"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import replace
from uuid import UUID

import pytest
from test_sync_port_predecision_phase import rig as rig

from pitchlog.repositories import transaction as tx
from pitchlog.repositories.binding import TenantBindingError
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync import port_guard
from pitchlog.sync.first_ball_recording_rights import (
    FirstBallRecordingRightsError,
    FirstBallRecordingRightsPort,
)
from pitchlog.sync.model import ABSENT
from pitchlog.sync.ports import _issue_port_writer, require_registered_port
from pitchlog.sync.tokens import PortCheckPresentedRightToken

_RAW = bytes(range(32))
_V12 = base64.urlsafe_b64encode(_RAW).rstrip(b"=").decode()


def test_actual_port_guard_accepts_closed_port_but_rejects_crypto_import():
    """実guardの許可/拒否を維持し、cryptoをPort閉包へ追加しない。"""
    require_registered_port(FirstBallRecordingRightsPort())
    with pytest.raises(RuntimeError):
        port_guard.validate_port_modules(("pitchlog.sync.first_ball_proof",))


@pytest.mark.parametrize("method", ["precheck", "commit", "right"])
@pytest.mark.parametrize("value", [True, False])
def test_stateless_port_returns_only_actual_writer_result(method, value):
    """呼出毎の命令を送り固定Trueや独自codecで代替しない。"""
    seen = []
    writer = _issue_port_writer(
        lambda token: seen.append(token) or TenantOperationResult(((value,),))
    )
    port = FirstBallRecordingRightsPort()
    if method == "precheck":
        result = port.read_rg1_before_d5(writer)
        assert type(seen[0]).__name__ == "PortRG1PrecheckToken"
    elif method == "commit":
        result = port.check_rg1_before_commit(writer)
        assert type(seen[0]).__name__ == "PortRG1CommitCheckToken"
    else:
        result = port.holds_recording_right(str(UUID(int=5)), "opaque-d4", _V12, writer)
        assert type(seen[0]) is PortCheckPresentedRightToken
        assert seen[0].raw_v12 is _V12
        assert _V12 not in repr(seen[0])
    assert result is value and len(seen) == 1
    writer._close()


@pytest.mark.parametrize(
    "rows", [(), ((None,),), ((1,),), ((True, False),), ((True,), (False,))]
)
def test_port_result_is_exact_bool(rows):
    """未知結果はfalseへ畳まず固定失敗にする。"""
    writer = _issue_port_writer(lambda _: TenantOperationResult(rows))
    with pytest.raises(FirstBallRecordingRightsError):
        FirstBallRecordingRightsPort().read_rg1_before_d5(writer)
    writer._close()


def test_p3_is_explicitly_unsupported():
    """P3を現loanや固定Falseで置き換えない。"""
    seen = []
    writer = _issue_port_writer(
        lambda token: seen.append(token) or TenantOperationResult(())
    )
    with pytest.raises(FirstBallRecordingRightsError, match="未提供"):
        FirstBallRecordingRightsPort().is_recovery_generation_current(
            str(UUID(int=5)), "old", writer
        )
    assert seen == []
    writer._close()


@pytest.mark.parametrize(
    "raw", [ABSENT, None, False, 1, "", "!" * 43, "x" * 42, _V12 + "=", "あ" * 43]
)
def test_bad_presented_proof_has_no_right_sql_or_loan_read(rig, monkeypatch, raw):
    """実codecの不正形式だけFalse、未確認epochやDB結果を捏造しない。"""
    seen = []
    monkeypatch.setattr(
        tx._TenantTransaction, "run_function", lambda *args: seen.append(args)
    )
    with tx._port_predecision_phase(rig.handle, "rights"):
        assert (
            FirstBallRecordingRightsPort().holds_recording_right(
                str(UUID(int=5)), "opaque-d4", raw, rig.writer
            )
            is False
        )
    assert seen == [] and rig.statements == [] and rig.loan_calls == []


@pytest.mark.parametrize(
    "rows,expected",
    [
        (((True, True),), True),
        (((True, False),), False),
        (((False, False),), None),
        (((False, True),), None),
    ],
)
def test_actual_codec_server_epoch_and_two_bool_mapping(
    rig, monkeypatch, rows, expected
):
    """raw32 digestと実借用由来epochを同binding命令へ渡し2boolを区分する。"""
    seen = []

    def fixed(self, token):
        seen.append(token)
        return TenantOperationResult(rows)

    monkeypatch.setattr(tx._TenantTransaction, "run_function", fixed)
    with tx._port_predecision_phase(rig.handle, "rights"):
        if expected is None:
            with pytest.raises(TenantBindingError, match="復旧世代"):
                FirstBallRecordingRightsPort().holds_recording_right(
                    str(UUID(int=5)), "opaque-d4", _V12, rig.writer
                )
        else:
            assert (
                FirstBallRecordingRightsPort().holds_recording_right(
                    str(UUID(int=5)), "opaque-d4", _V12, rig.writer
                )
                is expected
            )
    assert len(seen) == 1 and rig.loan_calls == [rig.loan]
    token = seen[0]
    assert token.recovery_generation == 902
    assert token.proof_digest == hashlib.sha256(_RAW).digest()
    assert token.proof_digest != hashlib.sha256(_V12.encode()).digest()
    lease = rig.bound._lease
    assert (
        token.attempt_id,
        token.phase_id,
        token.binding_nonce,
        token.device_id,
        token.game_id,
    ) == (lease.attempt_id, lease.phase_id, lease.nonce, lease.device_id, lease.game_id)


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "unknown",
        "bool",
        "zero",
        "big",
        "channel",
        "replaced",
        "backend",
        "database",
        "server",
    ],
)
def test_unheld_or_wrong_loan_never_reaches_right_sql(rig, monkeypatch, fault):
    """別型/不正epoch/切断/途中置換は固定epochに補完せず失敗する。"""
    from pitchlog.recording_rights.rg1_lifecycle import _GateLoan

    seen = []
    monkeypatch.setattr(
        tx._TenantTransaction, "run_function", lambda *a: seen.append(a)
    )
    if fault == "missing":
        tx._RG1_LOANS.pop(rig.handle._state_key)
    elif fault == "unknown":
        monkeypatch.setitem(tx._RG1_LOANS, rig.handle._state_key, object())
    elif fault in {"bool", "zero", "big"}:
        object.__setattr__(
            rig.loan._activation,
            "epoch",
            {"bool": True, "zero": 0, "big": 2**63}[fault],
        )
    elif fault in {"backend", "database", "server"}:
        changes = {
            "backend": {"backend_pid": rig.loan.binding.backend_pid + 1},
            "database": {"database_oid": rig.loan.binding.database_oid + 1},
            "server": {"system_identifier": "987654321"},
        }
        rig.loan.binding = replace(rig.loan.binding, **changes[fault])
    elif fault == "channel":

        def fail(self):
            raise RuntimeError("public pure loan fault")

        monkeypatch.setattr(_GateLoan, "assert_held", fail)
    else:

        def replace_loan(self):
            tx._RG1_LOANS.pop(rig.handle._state_key)

        monkeypatch.setattr(_GateLoan, "assert_held", replace_loan)
    with tx._port_predecision_phase(rig.handle, "rights"):
        with pytest.raises(RuntimeError):
            FirstBallRecordingRightsPort().holds_recording_right(
                str(UUID(int=5)), "opaque-d4", _V12, rig.writer
            )
    assert seen == [] and rig.statements == []


@pytest.mark.parametrize("kind", ["rg1-precheck", "rg1-commit", "device", "content"])
def test_raw_right_command_other_phase_is_sql_zero(rig, monkeypatch, kind):
    """proofを他phaseへ貸与しない。"""
    seen = []
    monkeypatch.setattr(
        tx._TenantTransaction, "run_function", lambda *a: seen.append(a)
    )
    with tx._port_predecision_phase(rig.handle, kind):
        with pytest.raises(TenantBindingError):
            rig.writer.run(PortCheckPresentedRightToken(UUID(int=5), "opaque-d4", _V12))
    assert seen == [] and rig.statements == [] and rig.loan_calls == []


@pytest.mark.parametrize(
    "field,value", [("game_id", UUID(int=92)), ("wire_d4", "different")]
)
def test_wrong_actual_binding_is_sql_zero(rig, monkeypatch, field, value):
    """別game/元D4差替えをcodecやloanより前に拒否する。"""
    seen = []
    monkeypatch.setattr(
        tx._TenantTransaction, "run_function", lambda *a: seen.append(a)
    )
    command = replace(
        PortCheckPresentedRightToken(UUID(int=5), "opaque-d4", _V12), **{field: value}
    )
    with tx._port_predecision_phase(rig.handle, "rights"):
        with pytest.raises(TenantBindingError):
            rig.writer.run(command)
    assert seen == [] and rig.loan_calls == []


@pytest.mark.parametrize("kind", ["rg1-precheck", "rg1-commit"])
@pytest.mark.parametrize("value", [True, False])
def test_rg1_true_rechecks_loan_false_does_not_invent_one(
    rig, monkeypatch, kind, value
):
    """両RG1命令のDB trueだけを実loanと再照合する。"""
    monkeypatch.setattr(
        tx._TenantTransaction,
        "run_function",
        lambda *a: TenantOperationResult(((value,),)),
    )
    port = FirstBallRecordingRightsPort()
    with tx._port_predecision_phase(rig.handle, kind):
        call = (
            port.read_rg1_before_d5
            if kind == "rg1-precheck"
            else port.check_rg1_before_commit
        )
        assert call(rig.writer) is value
    assert rig.loan_calls == ([rig.loan] if value else [])
