"""実行dispatcherの固定SQL選択・上限と、資格失敗時SQL0を純検査する。"""

from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from pitchlog.repositories import play_export_primitives as reads
from pitchlog.repositories import transaction as runtime
from pitchlog.repositories.binding import TenantBindingError
from pitchlog.repositories.stats import ReadPrimitiveTotalsToken
from pitchlog.repositories.stats_function_codec import StatsFunctionCodecError
from pitchlog.stats.generated.receiver import METRIC_IDS, SOURCE_MODEL_HASH

U = UUID(int=1)
V = UUID(int=2)
H = "a" * 64


def _operation(kind):
    """正式三tokenの値を構成する。値自身は資格にしない。"""
    if kind == "open":
        return reads.OpenPrimitiveSnapshotToken(U, V, SOURCE_MODEL_HASH)
    values = (U, V, U, 1, H, SOURCE_MODEL_HASH)
    if kind == "page":
        return reads.ReadPrimitivePageToken(*values, None, None, None, 1)
    return ReadPrimitiveTotalsToken(*values)


def _rows(kind):
    """正式codecの全列を欠落なく用意する。"""
    if kind == "open":
        return ((U, 1, H, SOURCE_MODEL_HASH, 1, 26, "1:2:", "current_open"),)
    if kind == "page":
        return ((METRIC_IDS[0], "available", Decimal(1), 0, U),)
    return tuple((metric, "source_unavailable", None) for metric in METRIC_IDS)


def _runtime(monkeypatch, operation, rows, *, qualification=None):
    """DBではなく記録可能な単位driverと、制御した資格前提を置く。"""
    calls = []
    key = object()
    handle = SimpleNamespace(_state_key=key)

    def execute(statement, parameters):
        calls.append((statement, parameters))
        return iter(rows)

    session = SimpleNamespace(execute=execute)
    monkeypatch.setitem(runtime._TRANSACTION_RUNTIMES, key, (session, None))
    monkeypatch.setattr(runtime, "_require_stats_primitive_read_scope", lambda h: None)
    monkeypatch.setattr(
        reads,
        "_qualified_stats_read_call",
        qualification
        or (
            lambda h, op: SimpleNamespace(
                operation=operation,
                transaction_id=None
                if type(op) is reads.OpenPrimitiveSnapshotToken
                else "1:2:",
            )
        ),
        raising=False,
    )
    return handle, calls


@pytest.mark.parametrize("kind", ["open", "page", "totals"])
def test_same_session_fixed_read_sql_and_complete_rows(monkeypatch, kind):
    """資格後の三固定SQLと全戻り値を保持し、tenant引数を追加しない。"""
    operation = _operation(kind)
    rows = _rows(kind)
    handle, calls = _runtime(monkeypatch, operation, rows)
    assert runtime._run_stats_primitive_read(handle, operation).rows == rows
    assert len(calls) == 1
    assert "stats_api." in str(calls[0][0])
    assert "tenant_id" not in calls[0][1]
    if kind != "open":
        assert "1:2:" in calls[0][1].values()


@pytest.mark.parametrize("kind", ["open", "page", "totals"])
def test_missing_private_qualification_executes_no_sql(monkeypatch, kind):
    """private資格失敗を成功応答やSQL試行へ変えない。"""

    def deny(handle, operation):
        raise TenantBindingError("未発行")

    operation = _operation(kind)
    handle, calls = _runtime(monkeypatch, operation, (), qualification=deny)
    with pytest.raises(TenantBindingError):
        runtime._run_stats_primitive_read(handle, operation)
    assert calls == []


@pytest.mark.parametrize("kind", ["open", "page", "totals"])
def test_excess_rows_are_rejected(monkeypatch, kind):
    """上限+1行を観測して拒否し、切り捨て成功にしない。"""
    operation = _operation(kind)
    rows = _rows(kind)
    handle, calls = _runtime(monkeypatch, operation, rows + rows)
    with pytest.raises(StatsFunctionCodecError):
        runtime._run_stats_primitive_read(handle, operation)
    assert len(calls) == 1


def test_another_operation_identity_executes_no_sql(monkeypatch):
    """同じ全値でも別tokenへ資格を移植しない。"""
    operation = _operation("open")
    handle, calls = _runtime(monkeypatch, _operation("open"), ())
    with pytest.raises(TenantBindingError):
        runtime._run_stats_primitive_read(handle, operation)
    assert calls == []


def test_missing_root_rrro_scope_executes_no_sql(monkeypatch):
    """値資格を得る前に、実root scope拒否を伝播する。"""
    operation = _operation("open")
    handle, calls = _runtime(monkeypatch, operation, ())

    def deny(handle):
        raise TenantBindingError("実scope無し")

    monkeypatch.setattr(runtime, "_require_stats_primitive_read_scope", deny)
    with pytest.raises(TenantBindingError):
        runtime._run_stats_primitive_read(handle, operation)
    assert calls == []


@pytest.mark.parametrize("transaction", [None, 1, ""])
def test_page_without_real_transaction_value_executes_no_sql(monkeypatch, transaction):
    """private資格の異常なsnapshot値を補完しない。"""
    operation = _operation("page")
    handle, calls = _runtime(
        monkeypatch,
        operation,
        (),
        qualification=lambda h, op: SimpleNamespace(
            operation=operation, transaction_id=transaction
        ),
    )
    with pytest.raises(StatsFunctionCodecError):
        runtime._run_stats_primitive_read(handle, operation)
    assert calls == []
