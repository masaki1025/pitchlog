"""実getter/実dispatcherの資格境界。E1 issuerとSQL結果は明示double。"""

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from test_nonplay_prefix import rig as rig

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.repositories import nonplay_qualification as api
from pitchlog.repositories import transaction as tx
from pitchlog.repositories.function_operations import FunctionOperationError
from pitchlog.sync.undo_execution import _undo_qualification_scope

_REAL_RUN_FUNCTION = tx._TenantTransaction.run_function


@pytest.fixture
def function_rig(rig, monkeypatch):
    """実transaction.run_functionを使いSQL結果だけをdoubleへ差替える。"""
    monkeypatch.setattr(tx._TenantTransaction, "run_function", _REAL_RUN_FUNCTION)
    rig.sql = []
    rig.sql_fault = None
    rig.sql_rows = None

    def execute(statement, parameters):
        name = statement.get_final_froms()[0].element.name
        rig.sql.append((name, dict(parameters)))
        if rig.sql_fault is not None:
            raise rig.sql_fault
        if rig.sql_rows is not None:
            return iter(rig.sql_rows)
        if name == "bind_nonplay_device":
            return iter(((True,),))
        if name == "check_nonplay_right":
            return iter(((True, True),))
        if name == "lock_nonplay_checkpoint":
            value = {
                "checkpoint": rig.value["checkpoint"],
                "storage": {
                    "row": {"real_row_fixture": "not-a-DB-proof"},
                    "nextPhysicalPlayNumber": rig.actual_next_physical,
                },
                "generationChain": rig.chain,
            }
            return iter(((_canonical_json(value),),))
        if name == "read_nonplay_history_page":
            request = json.loads(parameters["request_json"])
            return iter(
                tuple((_canonical_json(item),) for item in rig.records)
                if request["cursor"] is None
                else ()
            )
        assert name in {"prepare_nonplay_undo", "consume_nonplay_undo"}
        return iter(((True,),))

    rig.runtime[0].execute = execute
    try:
        yield rig
    finally:
        tx._PORT_DEVICE_BIND_USED.discard(rig.handle._state_key)
        assert not api._RIGHT_CALLS


@contextmanager
def decision_phase(rig, monkeypatch, kind):
    """実issuerの代用となるphase doubleを同source/handleへ限定する。"""
    old = rig.source.bound._phase_snapshot
    snapshot = json.dumps({"phase": {"internal_generation": 7, "wire_d4": "1"}})
    rig.source.bound._phase_snapshot = snapshot
    rig.source.bound.assert_current = lambda: None
    phase = SimpleNamespace(
        handle=rig.handle,
        runtime=rig.runtime,
        lifetime=rig.handle._writer_lifetime(),
        context=rig.handle._context,
        bound=rig.source.bound,
        snapshot=snapshot,
        kind=kind,
    )
    try:
        with monkeypatch.context() as patch:
            patch.setattr(tx, "_port_phase", lambda _h: phase)
            yield phase
    finally:
        rig.source.bound._phase_snapshot = old


@pytest.mark.parametrize("kind", ["device", "rights"])
def test_actual_phase_and_one_use_token_reach_fixed_sql(
    function_rig, monkeypatch, kind
):
    """既E1資格のみで実固定device/rightへ到達し、target/hostを先取りしない。"""
    r = function_rig
    with _undo_qualification_scope(r.handle, r.source):
        with decision_phase(r, monkeypatch, kind):
            result = (
                api.run_nonplay_device(r.handle, b"c" * 32)
                if kind == "device"
                else api.run_nonplay_right(r.handle, 3, b"p" * 32)
            )
    assert result.rows == (((True,),) if kind == "device" else ((True, True),))
    name, params = r.sql[0]
    assert name == (
        "bind_nonplay_device" if kind == "device" else "check_nonplay_right"
    )
    assert params["binding_nonce"] == r.lease.nonce
    assert params["game_id"] == r.lease.game_id
    if kind == "rights":
        assert params["internal_generation"] == 7
        assert params["recovery_generation"] == 3


def test_free_or_expired_right_token_cannot_execute(function_rig, monkeypatch):
    """同値clone/二度消費/終了後の再使用をSQL0で拒否する。"""
    r = function_rig
    with _undo_qualification_scope(r.handle, r.source):
        with decision_phase(r, monkeypatch, "device"):
            with api._right_call(
                r.handle, api.BindNonplayDeviceToken, {"credential_digest": b"c" * 32}
            ) as token:
                clone = object.__new__(api.BindNonplayDeviceToken)
                for field in api.fields(token):
                    object.__setattr__(clone, field.name, getattr(token, field.name))
                with pytest.raises(FunctionOperationError):
                    r.handle.run_function(clone)
                assert not r.sql
                assert r.handle.run_function(token).rows == ((True,),)
                with pytest.raises(FunctionOperationError):
                    r.handle.run_function(token)
    with pytest.raises(FunctionOperationError):
        r.handle.run_function(token)
    assert len(r.sql) == 1


@pytest.mark.parametrize(
    "fault",
    [
        "unqualified",
        "wrong-phase",
        "nonce",
        "nonce-type",
        "expired-tx",
        "runtime",
        "token-value",
        "bad-credential",
        "bad-generation",
    ],
)
def test_right_qualification_mutants_refuse_before_sql(
    function_rig, monkeypatch, fault
):
    """bool/nonce/型/寿命/別phaseの入力でdevice/rightを生成しない。"""
    r = function_rig
    if fault == "unqualified":
        with decision_phase(r, monkeypatch, "device"):
            with pytest.raises(RuntimeError):
                api.run_nonplay_device(r.handle, b"c" * 32)
        assert not r.sql
        return
    with _undo_qualification_scope(r.handle, r.source):
        with decision_phase(
            r, monkeypatch, "rights" if fault == "bad-generation" else "device"
        ) as phase:
            if fault in {"wrong-phase", "bad-credential", "bad-generation"}:
                if fault == "wrong-phase":
                    phase.kind = "content"
                with pytest.raises(RuntimeError):
                    if fault == "bad-generation":
                        api.run_nonplay_right(r.handle, True, b"p" * 32)
                    else:
                        api.run_nonplay_device(
                            r.handle, b"c" if fault == "bad-credential" else b"c" * 32
                        )
            else:
                with pytest.raises(RuntimeError):
                    with api._right_call(
                        r.handle,
                        api.BindNonplayDeviceToken,
                        {"credential_digest": b"c" * 32},
                    ) as token:
                        if fault == "nonce":
                            r.lease.nonce = b"y" * 32
                        elif fault == "nonce-type":
                            r.lease.nonce = bytearray(b"x" * 32)
                        elif fault == "expired-tx":
                            r.top.is_active = False
                        elif fault == "runtime":
                            monkeypatch.setitem(
                                tx._TRANSACTION_RUNTIMES,
                                r.handle._state_key,
                                (object(), object()),
                            )
                        else:
                            object.__setattr__(token, "credential_digest", b"y" * 32)
                        r.handle.run_function(token)
                # 元scopeの終了検査へ故障を持ち越さない（SQL0対向の後始末）。
                r.lease.nonce = b"x" * 32
                r.top.is_active = True
                monkeypatch.setitem(
                    tx._TRANSACTION_RUNTIMES, r.handle._state_key, r.runtime
                )
    assert not r.sql


@pytest.mark.parametrize(
    "fault", ["nonce", "lease-clone", "snapshot", "runtime", "top-tx"]
)
def test_rights_rechecks_actual_identity_after_sql(function_rig, monkeypatch, fault):
    """SQL返却後のlease/phase/TX差替えでも成功結果を返さない。"""
    r = function_rig
    original_execute = r.runtime[0].execute
    original_lease = r.source.bound._lease
    with _undo_qualification_scope(r.handle, r.source):
        with decision_phase(r, monkeypatch, "device") as phase:
            snapshot = phase.snapshot

            def execute(statement, parameters):
                result = original_execute(statement, parameters)
                if fault == "nonce":
                    r.lease.nonce = b"z" * 32
                elif fault == "lease-clone":
                    r.source.bound._lease = SimpleNamespace(**vars(r.lease))
                elif fault == "snapshot":
                    phase.snapshot = "changed"
                elif fault == "runtime":
                    monkeypatch.setitem(
                        tx._TRANSACTION_RUNTIMES,
                        r.handle._state_key,
                        (object(), object()),
                    )
                else:
                    r.top.is_active = False
                return result

            r.runtime[0].execute = execute
            with pytest.raises(RuntimeError):
                api.run_nonplay_device(r.handle, b"c" * 32)
            r.lease.nonce = b"x" * 32
            r.source.bound._lease = original_lease
            phase.snapshot = snapshot
            r.top.is_active = True
            monkeypatch.setitem(
                tx._TRANSACTION_RUNTIMES, r.handle._state_key, r.runtime
            )
    assert len(r.sql) == 1


def test_rights_missing_formal_sql_is_not_content_false(function_rig, monkeypatch):
    """未配置の実関数例外をFalse/成功へ変換しない。"""
    r = function_rig
    r.sql_fault = RuntimeError("missing formal SQL profile")
    with _undo_qualification_scope(r.handle, r.source):
        with decision_phase(r, monkeypatch, "rights"):
            with pytest.raises(RuntimeError, match="missing formal SQL profile"):
                api.run_nonplay_right(r.handle, 3, b"p" * 32)
    assert len(r.sql) == 1
