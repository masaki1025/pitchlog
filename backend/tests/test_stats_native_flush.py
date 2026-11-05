"""同TX flushを実型・唯一T5・明示した無DB Session doubleで検証する。"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session
from test_stats_native_connection import MODES
from test_stats_native_connection import native as source_fixture

from pitchlog.repositories import transaction as tx
from pitchlog.repositories.context import _ISSUANCE_CAPABILITY, TenantContext
from pitchlog.repositories.stats_function_codec import StatsFunctionCodecError
from pitchlog.stats.facts import SavePrimitiveSourceToken
from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH
from pitchlog.sync import first_ball_bridge as bridge
from pitchlog.sync import first_ball_execution as first
from pitchlog.sync import ordinary_pitch_execution as ordinary
from pitchlog.sync import stats_native_flush as api
from pitchlog.sync.stats_native_hook import StatsNativeSourceError


class _InjectedFailure(RuntimeError):
    """結果不明等の合成故障を固定文言で識別する。"""


class _Rows:
    """上限+1を超えて読まないこととcloseを観測する無DB結果。"""

    def __init__(self, values, *, fail=False):
        """全件fetchの代用品でなく行境界を観測する。"""
        self.values, self.fail = values, fail
        self.read = 0
        self.closed = False

    def __iter__(self):
        """各行の実消費だけを数える。"""
        for value in self.values:
            self.read += 1
            if self.fail:
                raise _InjectedFailure("synthetic result unavailable")
            yield value

    def close(self):
        """cursor終了を観測する。"""
        self.closed = True


@pytest.fixture(params=MODES)
def flush_rig(request, monkeypatch):
    """本物Session/transaction型を無bindで作り、SQL/認可はpure doubleと明記する。"""
    generator = cast(Any, source_fixture).__wrapped__(request, monkeypatch)
    r = next(generator)
    session = Session()
    session.begin()
    runtime = (session, object())
    lifetime = (r.key, session.get_transaction())
    monkeypatch.setitem(tx._TRANSACTION_RUNTIMES, r.key, runtime)
    r.state.runtime = runtime
    r.state.lifetime = lifetime
    r.bound._owner = lifetime
    if r.mode == MODES[0]:
        bridge._STATES[r.state.bridge].runtime = runtime
        bridge._STATES[r.state.bridge].lifetime = lifetime
    r.session = session
    r.before = [(0, None)]
    r.after = [(UUID(int=909), r.event_row["id"], SOURCE_MODEL_HASH, "b" * 64)]
    r.calls, r.results = [], []
    r.after_execute = None
    r.fail_at = None
    r.fail_fetch_at = None
    r.prepare_calls = []
    r.transaction_controls = []
    prepare = api.prepare_native_evaluation

    def preparing(payload, **kwargs):
        r.prepare_calls.append((payload, kwargs))
        return prepare(payload, **kwargs)

    monkeypatch.setattr(api, "prepare_native_evaluation", preparing)

    def execute(statement, parameters):
        # 明示した固定2statementの同Session呼出だけを合成する。
        r.calls.append((statement, parameters))
        n = len(r.calls)
        if r.fail_at == n:
            raise _InjectedFailure("synthetic SQL unavailable")
        result = _Rows(r.before if n == 1 else r.after, fail=r.fail_fetch_at == n)
        r.results.append(result)
        if r.after_execute is not None:
            r.after_execute(n)
        return result

    monkeypatch.setattr(session, "execute", execute)

    def forbidden_control(*args, **kwargs):
        r.transaction_controls.append(True)
        raise AssertionError("flush must not own commit/rollback/savepoint")

    for name in ("commit", "rollback", "begin_nested"):
        monkeypatch.setattr(session, name, forbidden_control)
    try:
        yield r
    finally:
        generator.close()
        session.close()


def _flush(r, **kwargs):
    """入口の値部品を組立てず本物source発行から始める。"""
    return api._flush_native_stats(
        r.handle, r.writer, r.event, r.projected, generation=kwargs.get("generation", 1)
    )


def test_actual_source_preflight_one_t5_save_same_session(flush_rig):
    """全4modeで固定SQL2本と唯一生成T5へ流れ、戻り全4列を保持する。"""
    r = flush_rig
    result = _flush(r)
    assert result.rows == tuple(r.after)
    assert len(r.calls) == 2 and len(r.prepare_calls) == 1
    assert "stats_api.read_primitive_writer_state" in str(r.calls[0][0])
    assert "stats_api.save_primitive_source" in str(r.calls[1][0])
    assert set(r.calls[0][1]) == {
        "attempt_id",
        "phase_id",
        "source_event_id",
        "model_sha256",
        "binding_nonce",
    }
    assert len(r.calls[1][1]) == 8
    first_params, save_params = r.calls[0][1], r.calls[1][1]
    for key in first_params:
        assert first_params[key] == save_params[key]
    assert first_params["source_event_id"] == r.event_row["id"]
    assert first_params["binding_nonce"] == r.bound._lease.nonce
    assert save_params["expected_revision"] == 0
    assert save_params["expected_source_set_sha256"] is None
    envelope = json.loads(save_params["evaluation_json"])
    assert envelope["source_event_id"] == str(r.event_row["id"])
    assert envelope["selected"] is True
    assert envelope["native_rule_sha256"] == api.native.source_fingerprint(
        r.prepare_calls[0][0]["calculation"]["request"]["rules"]
    )
    assert api.native._json(r.prepare_calls[0][0]) == api.native._json(r.event.v7)
    assert all(result.closed and result.read == 1 for result in r.results)
    assert r.transaction_controls == []
    with pytest.raises(StatsNativeSourceError):
        _flush(r)
    assert len(r.calls) == 2


def test_positive_actual_revision_and_old_s_bind_cas_without_comparing_new_s(flush_rig):
    """D1からrevisionを推測せず実前値をそのままCASへ渡す。"""
    r = flush_rig
    r.before = [(37, "a" * 64)]
    result = _flush(r)
    assert result.rows[0][3] == "b" * 64
    assert r.calls[1][1]["expected_revision"] == 37
    assert r.calls[1][1]["expected_source_set_sha256"] == "a" * 64
    assert r.prepare_calls[0][1]["expected_revision"] == 37
    assert r.transaction_controls == []


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [(0, None), (0, None)],
        [(False, None)],
        [(-1, None)],
        [(0, "a" * 64)],
        [(1, None)],
        [(1, "wrong")],
        [(1, None, "extra")],
    ],
)
def test_preflight_missing_extra_or_bad_cas_never_calls_t5_or_save(flush_rig, rows):
    """不在推測やbool=intを許さずT5前に閉じる。"""
    r = flush_rig
    r.before = rows
    with pytest.raises(StatsFunctionCodecError):
        _flush(r)
    assert len(r.calls) == 1 and r.prepare_calls == []
    assert r.transaction_controls == []


@pytest.mark.parametrize(
    "change", ["none", "extra", "width", "version", "source", "model", "s"]
)
def test_bad_four_column_save_result_is_not_success(flush_rig, change):
    """実SQL返りの欠落/余剰/版型/別source/model/不正Sを拒否する。"""
    r = flush_rig
    if change == "none":
        r.after = []
    elif change == "extra":
        r.after = r.after * 2
    elif change == "width":
        r.after = [r.after[0][:-1]]
    else:
        row = list(r.after[0])
        pos = {"version": 0, "source": 1, "model": 2, "s": 3}[change]
        row[pos] = {
            "version": str(uuid4()),
            "source": uuid4(),
            "model": "unknown",
            "s": "unknown",
        }[change]
        r.after = [tuple(row)]
    with pytest.raises(StatsFunctionCodecError):
        _flush(r)
    assert len(r.calls) == 2 and len(r.prepare_calls) == 1
    assert r.transaction_controls == []


def test_row_overflow_reads_only_upper_bound_plus_one(flush_rig):
    """未知の10000行を全件materializeせず2行で拒否する。"""
    r = flush_rig
    r.before = [(0, None)] * 10000
    with pytest.raises(StatsFunctionCodecError):
        _flush(r)
    assert r.results[0].read == 2 and r.results[0].closed
    assert r.prepare_calls == []


@pytest.mark.parametrize("when", [1, 2])
def test_sql_failure_propagates_to_outer_transaction_without_recovery(flush_rig, when):
    """SQL失敗を握り潰したり自前commit/rollbackで分離しない。"""
    r = flush_rig
    r.fail_at = when
    with pytest.raises(_InjectedFailure):
        _flush(r)
    assert len(r.calls) == when
    assert len(r.prepare_calls) == when - 1
    assert r.transaction_controls == []
    with pytest.raises(StatsNativeSourceError):
        _flush(r)


@pytest.mark.parametrize("when", [1, 2])
def test_result_unknown_propagates_and_closes_cursor(flush_rig, when):
    """fetch故障でも同資格での再実行や成功補完をしない。"""
    r = flush_rig
    r.fail_fetch_at = when
    with pytest.raises(_InjectedFailure):
        _flush(r)
    assert r.results[-1].closed
    assert r.transaction_controls == []


@pytest.mark.parametrize(
    "change", ["writer", "nonce", "execution", "runtime", "transaction", "context"]
)
def test_qualification_loss_after_preflight_stops_before_t5(
    flush_rig, monkeypatch, change
):
    """同じ値を持つ別scope/失効を前値成功から引き継がない。"""
    r = flush_rig

    def mutate(n):
        assert n == 1
        if change == "writer":
            r.writer._close()
        elif change == "nonce":
            r.bound._lease.nonce = b"x" * 32
        elif change == "execution":
            r.state.stats_source_reference = None
        elif change == "runtime":
            monkeypatch.setitem(tx._TRANSACTION_RUNTIMES, r.key, (Session(), object()))
        elif change == "transaction":
            r.session.get_transaction().close()
        else:
            r.handle._context = TenantContext(r.context.tenant_id, _ISSUANCE_CAPABILITY)

    r.after_execute = mutate
    with pytest.raises((api.StatsNativeFlushError, RuntimeError)):
        _flush(r)
    assert len(r.calls) == 1 and r.prepare_calls == []
    assert r.transaction_controls == []


@pytest.mark.parametrize("when", ["t5", "after_t5", "after_save"])
def test_midpoint_failure_never_returns_partial_success(flush_rig, monkeypatch, when):
    """故障の全rollbackは外TXへ委ね、本関数は例外を伝播する。"""
    r = flush_rig
    if when in ("t5", "after_t5"):
        original = api.prepare_native_evaluation

        def preparing(*args, **kwargs):
            if when == "t5":
                raise _InjectedFailure("synthetic T5 failure")
            token = original(*args, **kwargs)
            r.bound._lease.nonce = b"x" * 32
            return token

        monkeypatch.setattr(api, "prepare_native_evaluation", preparing)
    else:

        def mutate(n):
            if n == 2:
                r.state.stats_source_reference = None

        r.after_execute = mutate
    with pytest.raises(
        (
            api.StatsNativeFlushError,
            _InjectedFailure,
            first.FirstBallExecutionError,
            ordinary.OrdinaryPitchExecutionError,
        )
    ):
        _flush(r)
    assert len(r.calls) == (2 if when == "after_save" else 1)
    assert r.transaction_controls == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("attempt_id", UUID(int=99)),
        ("phase_id", UUID(int=99)),
        ("source_event_id", UUID(int=99)),
        ("model_sha256", "unknown"),
        ("expected_revision", False),
        ("expected_source_set_sha256", "a" * 64),
    ],
)
def test_prepared_token_must_match_full_actual_preflight_binding(
    flush_rig, monkeypatch, field, value
):
    """生成tokenのsource/model/CASを自由値で差し替えられない。"""
    r = flush_rig
    original = api.prepare_native_evaluation
    monkeypatch.setattr(
        api,
        "prepare_native_evaluation",
        lambda *a, **k: replace(original(*a, **k), **{field: value}),
    )
    with pytest.raises(api.StatsNativeFlushError):
        _flush(r)
    assert len(r.calls) == 1 and len(r.prepare_calls) == 1


@pytest.mark.parametrize("change", ["nonce", "writer", "read_scope", "generation"])
def test_invalid_entry_does_not_execute_stats_sql(flush_rig, monkeypatch, change):
    """不成立のsourceを仮成功で迂回せずSession.execute0にする。"""
    r = flush_rig
    if change == "nonce":
        r.bound._lease.nonce = b"x" * 32
    elif change == "writer":
        r.writer._close()
    elif change == "read_scope":
        monkeypatch.setitem(tx._STATS_READ_HANDLES, r.key, object())
    with pytest.raises(
        (
            api.StatsNativeFlushError,
            StatsNativeSourceError,
            first.FirstBallExecutionError,
            ordinary.OrdinaryPitchExecutionError,
        )
    ):
        _flush(r, generation=2 if change == "generation" else 1)
    assert r.calls == [] and r.prepare_calls == []


def test_public_save_value_token_still_has_no_direct_function_registration(flush_rig):
    """直接run_functionへ自由tokenを持込んでもSQLへ到達しない。"""
    r = flush_rig
    token = SavePrimitiveSourceToken(
        uuid4(), uuid4(), r.event_row["id"], SOURCE_MODEL_HASH, 0, None, "{}"
    )
    with pytest.raises(RuntimeError):
        r.handle.run_function(token)
    assert r.calls == []


@pytest.mark.parametrize(
    "change", ["extra", "wrong_source", "false_selection", "numeric_value"]
)
def test_t5_envelope_corruption_cannot_be_saved(flush_rig, monkeypatch, change):
    """唯一評価の後でも閉schema/sourceと異なる値を保存へ送らない。"""
    r = flush_rig
    original = api.prepare_native_evaluation

    def corrupt(*args, **kwargs):
        token = original(*args, **kwargs)
        data = json.loads(token.evaluation_json)
        if change == "extra":
            data["unexpected"] = True
        elif change == "wrong_source":
            data["source_event_id"] = str(UUID(int=99))
        elif change == "false_selection":
            data["selected"] = False
        else:
            data["metrics"][next(iter(data["metrics"]))]["value"] = 0.5
        return replace(token, evaluation_json=json.dumps(data))

    monkeypatch.setattr(api, "prepare_native_evaluation", corrupt)
    with pytest.raises((api.StatsNativeFlushError, StatsFunctionCodecError)):
        _flush(r)
    assert len(r.calls) == 1 and len(r.prepare_calls) == 1
    assert r.transaction_controls == []


@pytest.mark.parametrize("site", ["read_writer_state", "save_source"])
@pytest.mark.parametrize("mutation", ["missing", "clone"])
def test_actual_writer_registration_is_required_before_each_sql(
    flush_rig, monkeypatch, site, mutation
):
    """同値cloneや登録欠落をsource資格だけで補わず、対象SQLより前に拒否する。"""
    from pitchlog.repositories.function_operations import FunctionOperationError

    r = flush_rig
    original = tx.FUNCTION_OPERATION_REGISTRY
    selected = next(
        row
        for row in original.values()
        if row.operation_id == "STATS_PRIMITIVES:" + site
    )
    changed = dict(original)
    if mutation == "missing":
        del changed[selected.token_type]
    else:
        changed[selected.token_type] = replace(selected)
    monkeypatch.setattr(tx, "FUNCTION_OPERATION_REGISTRY", changed)
    with pytest.raises(FunctionOperationError):
        _flush(r)
    expected_calls = 0 if site == "read_writer_state" else 1
    assert len(r.calls) == expected_calls
    assert len(r.prepare_calls) == expected_calls
    assert all(result.closed for result in r.results)
