"""実Session/EngineのGCと借用終結順を確認する。PG/認可成功の証明ではない。"""

from __future__ import annotations

import gc
import weakref
from contextlib import contextmanager
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool
from test_authz_tenant_context import make_tenant_context

from pitchlog.repositories import rg1, transaction


@pytest.mark.parametrize("failure", ["none", "body", "precommit", "release", "close"])
def test_runtime_is_alive_until_loan_termination_and_then_collectible(
    monkeypatch, failure
):
    """元pop/closeの後でも、release/abandonが終わる前に実runtimeを失わない。"""
    events = []
    references = {}
    failure_object = RuntimeError("lifetime-unit-fixture")
    state_key = []

    def engine_factory():
        engine = create_engine("sqlite://", poolclass=QueuePool)
        references["engine"] = weakref.ref(engine)
        return engine

    class ObservedSession(Session):
        """本物のSQLAlchemy Session.closeを一回だけ呼び順序を観測する。"""

        def close(self):
            super().close()
            events.append("session-close")
            if failure == "close":
                raise failure_object

    def session_factory(engine):
        session = ObservedSession(engine)
        references["session"] = weakref.ref(session)
        return session

    @contextmanager
    def boundary(session, _context):
        # 実SQLite TXでcommit/rollback/接続返却を起こす。野球計算はしない。
        with session.begin():
            session.execute(text("SELECT 1"))
            try:
                yield
            except BaseException:
                events.append("rollback")
                raise
            else:
                events.append("commit")

    def before_commit(_handle):
        events.append("precommit")
        if failure == "precommit":
            raise failure_object

    def require_lifetime(terminal):
        assert "session-close" in events
        assert state_key[0] not in transaction._TRANSACTION_RUNTIMES
        gc.collect()
        assert references["session"]() is not None, (
            "Session died before loan termination"
        )
        assert references["engine"]() is not None, "Engine died before loan termination"
        events.append(terminal)

    class LoanProbe:
        """制御成功は模擬しない。scope終結中の物理資源寿命だけを観測する。"""

        def release(self):
            require_lifetime("release")
            if failure == "release":
                raise failure_object

        def abandon(self):
            require_lifetime("abandon")

    monkeypatch.setattr(transaction, "create_database_engine", engine_factory)
    monkeypatch.setattr(transaction, "Session", session_factory)
    monkeypatch.setattr(transaction, "_tenant_transaction", boundary)
    monkeypatch.setattr(rg1, "assert_rg1_open_before_commit", before_commit)
    context = make_tenant_context(UUID("00000000-0000-0000-0000-000000000779"))

    caught = None
    try:
        with transaction.tenant_transaction_scope(context) as handle:
            assert handle._state_key is not None
            state_key.append(handle._state_key)
            transaction._RG1_LOANS[handle._state_key] = cast(Any, LoanProbe())
            if failure == "body":
                raise failure_object
    except RuntimeError as error:
        caught = error
    assert (caught is None) if failure == "none" else (caught is failure_object)
    assert handle._state_key is None
    expected_terminal = "abandon" if failure == "close" else "release"
    assert events[-2:] == ["session-close", expected_terminal]
    assert not transaction._RG1_LOANS
    assert not transaction._TRANSACTION_RUNTIMES
    # close失敗では元traceback自身がselfを持つ。観測用tracebackを明示解放して調べる。
    # release失敗でもouter frameに恒久runtime参照が残らないことを含む。
    if caught is not None:
        caught.__traceback__ = None
    gc.collect()
    assert references["session"]() is None
    assert references["engine"]() is None


@pytest.mark.parametrize("boundary", ["scope", "release"])
@pytest.mark.parametrize("failure", ["none", "original", "gc"])
def test_owned_gc_observer_preserves_original_identity(
    monkeypatch, capsys, boundary, failure
):
    """試験用GC観測器の故障でも、元呼出一回と戻り/例外を置換しない。"""
    import json

    from db.test_rg1_scope_runtime_lifetime_owned import _GC_PROBE_SOURCE

    from pitchlog.recording_rights import rg1_lifecycle

    calls = []
    returned = object()
    original_error = RuntimeError("secret-sentinel-never-logged")

    def original(self, *args, **kwargs):
        calls.append(self)
        if failure == "original":
            raise original_error
        return returned

    owner = (
        transaction._TenantTransactionScope
        if boundary == "scope"
        else rg1_lifecycle._GateLoan
    )
    symbol = "__exit__" if boundary == "scope" else "release"
    monkeypatch.setattr(owner, symbol, original)
    namespace: dict[str, Any] = {"__name__": "_gc_observer_identity_probe"}
    exec(compile(_GC_PROBE_SOURCE, "<fixed-gc-probe>", "exec"), namespace)
    snapshot, restore = namespace["install_gc_probe"]()
    instance = object.__new__(owner)
    if boundary == "scope":
        assert isinstance(instance, transaction._TenantTransactionScope)
        instance._handle = None
    if failure == "gc":

        def broken_gc():
            raise RuntimeError("secret-sentinel-never-logged")

        monkeypatch.setattr(gc, "collect", broken_gc)
    try:
        if failure == "original":
            with pytest.raises(RuntimeError) as error:
                getattr(instance, symbol)()
            assert error.value is original_error
        else:
            assert getattr(instance, symbol)() is returned
        assert calls == [instance]
        assert "secret-sentinel" not in json.dumps(snapshot())
        assert capsys.readouterr().out == ""
    finally:
        restore()
