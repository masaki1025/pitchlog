"""実型と明示した無DB doubleで、台帳私有経路/再掲順/固定SQLを検証する。"""

from __future__ import annotations

import json
from contextlib import ExitStack
from dataclasses import replace
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Insert
from test_stats_native_connection import MODES
from test_stats_native_connection import native as source_fixture

from pitchlog.repositories import base
from pitchlog.repositories import transaction as tx
from pitchlog.sync import first_ball_bridge as bridge
from pitchlog.sync import native_ledger_insert as api
from pitchlog.sync.control_provider.writer_binding import _LiveWriterBinding
from pitchlog.sync.first_ball_frame import FirstBallFrameValue
from pitchlog.sync.idempotency import D5Candidate, StoredResult
from pitchlog.sync.source_binding import _E1CoreSource
from pitchlog.sync.tokens import IdempotencyLedgerInsertToken

_REAL_SOURCE_READ = _E1CoreSource.read
_REAL_BOUND_CURRENT = _LiveWriterBinding.assert_current


class _Failure(RuntimeError):
    """例外原値を持たない観測用故障。"""


class _Rows:
    """上限/実消費/closeを観測する、DB実証ではないcursor double。"""

    def __init__(self, values, *, fail=False):
        self.values, self.fail = values, fail
        self.read, self.closed = 0, False

    def __iter__(self):
        for row in self.values:
            self.read += 1
            if self.fail:
                raise _Failure("result unavailable")
            yield row

    def close(self):
        self.closed = True


def _stored(kind="stored_result"):
    if kind == "conflict":
        return D5Candidate("conflict", boundary="B3b")
    return D5Candidate(
        "stored_result",
        stored=StoredResult("accepted", "same", {"state": "受理", "d3": 1}, None),
    )


@pytest.fixture(params=MODES)
def rig(request, monkeypatch):
    """既規範封筒/本物型を使い、control/DBの合成を実認可と主張しない。"""
    generator = cast(Any, source_fixture).__wrapped__(request, monkeypatch)
    r = next(generator)
    session = Session()
    session.begin()
    runtime = (session, object())
    lifetime = (r.key, session.get_transaction())
    monkeypatch.setitem(tx._TRANSACTION_RUNTIMES, r.key, runtime)
    r.state.runtime, r.state.lifetime, r.bound._owner = runtime, lifetime, lifetime
    r.state.phase = "ready"
    if r.mode == MODES[0]:
        state = bridge._STATES[r.state.bridge]
        state.runtime, state.lifetime = runtime, lifetime
        state.phase, state.frame = "ready", r.state.frame
        payload = r.state.payload.v7
        state.value = FirstBallFrameValue(
            r.context.tenant_id,
            UUID(r.event.game_id),
            1,
            r.event.d1,
            UUID(r.event.d5),
            r.view.event_fingerprint,
            payload.calculation.artifact_sha256,
            payload.calculation.request.model_dump_json(by_alias=True),
            payload.calculation.response.model_dump_json(by_alias=True),
            "{}",  # この試験は実roster/issuer/数学を成立扱いにしない。
        )
    else:
        r.state.frame = r.state.stats_source_reference[0]
        r.state.preparation_used = False
    r.session = session
    r.token = IdempotencyLedgerInsertToken(
        UUID(r.event.d5),
        "accepted",
        r.view.event_fingerprint,
        json.dumps({"state": "受理", "d3": r.event.d1, "temporary_id_mapping": {}}),
    )
    r.calls, r.results, r.controls, r.classified = [], [], [], []
    r.result = [(1,)]
    r.candidates = [D5Candidate("unused")]
    r.after_execute = None
    r.fail_execute = r.fail_fetch = False

    def classify(handle, d5, fingerprint, path):
        assert handle is r.handle
        assert (d5, fingerprint, path) == (r.token.d5, r.token.source_fingerprint, "P2")
        r.classified.append((d5, fingerprint, path))
        return r.candidates.pop(0)

    monkeypatch.setattr(api, "classify_d5", classify)

    def execute(statement, parameters):
        r.calls.append((statement, parameters))
        if r.fail_execute:
            raise _Failure("SQL unavailable")
        cursor = _Rows(r.result, fail=r.fail_fetch)
        r.results.append(cursor)
        if r.after_execute is not None:
            r.after_execute()
        return cursor

    monkeypatch.setattr(session, "execute", execute)

    def forbidden(*args, **kwargs):
        r.controls.append(True)
        raise AssertionError("private insert cannot own transaction controls")

    for name in ("commit", "rollback", "begin_nested"):
        monkeypatch.setattr(session, name, forbidden)
    try:
        yield r
    finally:
        generator.close()
        session.close()


def _call(r, **changes):
    args: dict[str, Any] = dict(
        handle=r.handle, writer=r.writer, event=r.event, token=r.token, path="P2"
    )
    args.update(changes)
    return api._recheck_and_insert_native_result(**args)


def test_fresh_top_level_insert_preserves_validated_table_binds_and_generic_rejection(
    rig,
):
    """元prepare/tenant/typedbindを保持し、generic拡張は拒否のままにする。"""
    r = rig
    assert _call(r) is None
    assert len(r.calls) == len(r.results) == len(r.classified) == 1
    statement, parameters = r.calls[0]
    original, original_parameters = base._prepare_operation(
        r.token, r.context.tenant_id
    )
    assert isinstance(original, Insert) and original._values is not None
    assert statement.table is original.table
    assert (
        set(statement._values)
        == set(original._values)
        == {"tenant_id", "d5", "kind", "source_fingerprint", "result", "reason"}
    )
    assert all(
        statement._values[key].compare(value) for key, value in original._values.items()
    )
    assert parameters == original_parameters
    assert parameters["tenant_id"] == r.context.tenant_id
    assert statement.get_execution_options()["schema_translate_map"] == {None: "public"}
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            schema_translate_map={None: "public"},
            render_schema_translate=True,
        )
    )
    assert sql == (
        "INSERT INTO public.idempotency_ledger (d5, kind, source_fingerprint, result, "
        "reason, tenant_id) VALUES (%(d5)s::UUID, %(kind)s, %(source_fingerprint)s, "
        "%(result)s::JSONB, %(reason)s, %(tenant_id)s::UUID) ON CONFLICT ON CONSTRAINT "
        "pk_idempotency_ledger DO NOTHING RETURNING 1"
    )
    assert "UPDATE" not in sql
    with pytest.raises(base._TenantOperationError):
        base._validate_prepared_statement(
            base._operation_spec(r.token), statement, parameters
        )
    assert r.results[0].closed and not r.controls


def test_initial_stored_never_calls_fresh_qualification(rig, monkeypatch):
    """初回保存済みをfresh資格検査へ前倒ししない。"""
    r = rig
    candidate = _stored()
    r.candidates = [candidate]

    def forbidden(*args, **kwargs):
        raise _Failure("fresh must not precede replay")

    monkeypatch.setattr(api, "_fresh", forbidden)
    assert _call(r) is candidate
    assert not r.calls


@pytest.mark.parametrize("kind", ["stored_result", "conflict"])
def test_zero_return_reclassifies_before_fresh_postcheck_even_when_lease_expires(
    rig, monkeypatch, kind
):
    """競合待機中のlease失効より先に旧再掲/異内容を返す。"""
    r = rig
    r.result = []
    candidate = _stored(kind)
    r.candidates.append(candidate)
    original = api._fresh

    def fresh(*args, **kwargs):
        if r.calls:
            raise _Failure("expired lease/source after conflict wait")
        return original(*args, **kwargs)

    monkeypatch.setattr(api, "_fresh", fresh)
    r.after_execute = lambda: setattr(r.bound, "_used", True)
    assert _call(r) is candidate
    assert len(r.calls) == 1 and len(r.classified) == 2 and r.results[0].closed


def test_zero_return_unseen_winner_is_not_success(rig):
    """競合後の不可視を挿入成功や未使用へ補完しない。"""
    r = rig
    r.result = []
    r.candidates.append(D5Candidate("unused"))
    with pytest.raises(RuntimeError, match="先着行"):
        _call(r)
    assert len(r.classified) == 2 and r.results[0].closed


@pytest.mark.parametrize(
    "rows",
    [
        [(True,)],
        [(1.0,)],
        [(Decimal(1),)],
        [(0,)],
        [(2,)],
        [(1, 2)],
        [(1,), (1,)],
        [(1,), (1,), (1,)],
        [[1]],
        [{0: 1}],
        [()],
        [(None,)],
    ],
)
def test_non_exact_one_result_is_rejected_and_cursor_closed(rig, rows):
    """厳密int1以外の行を拒否し、結果cursorを必ず閉じる。"""
    r = rig
    r.result = rows
    with pytest.raises(api.NativeLedgerInsertError):
        _call(r)
    assert r.results[0].closed and r.results[0].read <= 2
    assert len(r.classified) == 1


@pytest.mark.parametrize(
    "failure", ["execute", "fetch", "post_control", "post_runtime"]
)
def test_failures_propagate_for_outer_rollback_without_local_transaction_control(
    rig, failure
):
    """SQL/読取/資格故障を伝播して外側全rollbackへ任せる。"""
    r = rig
    if failure == "execute":
        r.fail_execute = True
    elif failure == "fetch":
        r.fail_fetch = True
    elif failure == "post_control":
        r.after_execute = lambda: setattr(r.bound, "_used", True)
    else:
        r.after_execute = lambda: tx._TRANSACTION_RUNTIMES.pop(r.key)
    with pytest.raises((api.NativeLedgerInsertError, _Failure, RuntimeError)):
        _call(r)
    assert not r.controls
    if r.results:
        assert r.results[0].closed
    assert len(r.classified) == 1


@pytest.mark.parametrize(
    "change",
    [
        "wrong_writer",
        "writer_closed",
        "wrong_event",
        "context",
        "phase_closed",
        "frame_missing",
        "frame_anchor",
        "payload",
        "lease_nonce",
        "bound_used",
        "bound_registry",
        "source_scope",
        "source_event",
        "source_write",
        "source_phase",
        "mode",
        "nested",
        "port_phase",
        "actor",
        "rrro",
        "initial_runtime",
    ],
)
def test_fake_or_expired_private_qualification_does_not_insert(
    rig, change, monkeypatch
):
    """偽造/別scope/失効/native未準備からINSERTへ進まない。"""
    r = rig
    changes = {}
    if change == "wrong_writer":
        changes["writer"] = object()
    elif change == "writer_closed":
        r.writer._close()
    elif change == "wrong_event":
        changes["event"] = replace(r.event)
    elif change == "context":
        r.handle._bound_integrity_proof = object()
    elif change == "phase_closed":
        r.state.phase = "closed"
    elif change == "frame_missing":
        r.state.frame = None
    elif change == "frame_anchor":
        a = r.state.stats_source_reference
        r.state.stats_source_reference = (object(), *a[1:])
    elif change == "payload":
        r.state.payload = None
    elif change == "lease_nonce":
        r.bound._lease.nonce = b"x" * 32
    elif change == "bound_used":
        r.bound._used = True
    elif change == "bound_registry":
        monkeypatch.delitem(api._LIVE_BINDINGS, r.key)
    elif change == "source_scope":
        r.source.scope = object()
    elif change == "source_event":
        r.source.event = replace(r.event)
    elif change == "source_write":
        r.source.write_started = False
    elif change == "source_phase":
        r.source.phase = replace(r.source.phase)
    elif change == "mode":
        if r.mode == MODES[0]:
            r.state.assigned_d2 = 1
        else:
            r.state.mode = "unknown"
    elif change == "nested":
        monkeypatch.setattr(r.session, "in_nested_transaction", lambda: True)
    elif change == "port_phase":
        monkeypatch.setattr(tx, "_port_phase", lambda _: object())
    elif change == "actor":
        monkeypatch.setitem(tx._INITIAL_ACTOR_STATES, r.key, object())
    elif change == "rrro":
        monkeypatch.setitem(tx._STATS_READ_HANDLES, r.key, object())
    else:
        monkeypatch.delitem(tx._TRANSACTION_RUNTIMES, r.key)
    with pytest.raises((api.NativeLedgerInsertError, RuntimeError)):
        _call(r, **changes)
    assert not r.calls


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "rejected"),
        ("kind", True),
        ("reason", "unexpected"),
        ("d5", uuid4()),
        ("source_fingerprint", "unknown"),
        ("result_json", '{"state":"受理","d3":true,"temporary_id_mapping":{}}'),
        ("result_json", '{"state":"受理","d3":1,"d3":1,"temporary_id_mapping":{}}'),
        ("result_json", '{"state":"受理","d3":NaN,"temporary_id_mapping":{}}'),
        ("result_json", '{"state":"受理","d3":1,"temporary_id_mapping":{"x":"y"}}'),
        ("result_json", "{}"),
        ("result_json", "[]"),
        ("result_json", "{"),
    ],
)
def test_original_token_all_fields_cannot_be_changed_into_private_sql(
    rig, field, value
):
    """元tokenの各fieldの改変を任意INSERTへ変換しない。"""
    r = rig
    r.token = replace(r.token, **{field: value})
    with pytest.raises((api.NativeLedgerInsertError, AssertionError)):
        _call(r)
    assert not r.calls


def test_original_preflight_cannot_be_silently_skipped(rig, monkeypatch):
    """既登録へ将来追加されたpreflightを無視して実行しない。"""
    r = rig
    original = base._operation_spec(r.token)
    monkeypatch.setattr(
        base, "_operation_spec", lambda _: replace(original, preflight=object())
    )
    with pytest.raises(api.NativeLedgerInsertError):
        _call(r)
    assert not r.calls


@pytest.mark.parametrize("same", [True, False])
def test_zero_uses_actual_shared_d5_classifier_and_preserves_winner(
    rig, monkeypatch, same
):
    """0行後は既分類器を通し、先着原本を更新せず同値再掲/異内容へ分ける。"""
    from pitchlog.repositories.tokens import TenantOperationResult
    from pitchlog.sync.idempotency import classify_d5
    from pitchlog.sync.tokens import IdempotencyLedgerReadToken

    r = rig
    r.result = []
    if not same:
        r.ledger_row["source_fingerprint"] = "different winner fingerprint"
    reads = []
    old_run = tx._TenantTransaction.run

    def run(handle, token):
        if type(token) is IdempotencyLedgerReadToken:
            assert handle is r.handle and token.d5 == UUID(r.event.d5)
            reads.append(True)
            return TenantOperationResult(
                () if len(reads) == 1 else (tuple(r.ledger_row.values()),)
            )
        return old_run(handle, token)

    # writerとbridgeは実run method identityにも束縛されるので、差し替え後に再発行する。
    from pitchlog.sync.ports import _issue_port_writer

    monkeypatch.setattr(tx._TenantTransaction, "run", run)
    r.writer._close()
    r.writer = _issue_port_writer(r.handle.run)
    r.state.writer = r.writer
    if r.mode == MODES[0]:
        bridge._STATES[r.state.bridge].writer = r.writer
    monkeypatch.setattr(api, "classify_d5", classify_d5)
    winner = dict(r.ledger_row)
    candidate = _call(r)
    assert len(reads) == 2 and len(r.calls) == 1
    assert r.ledger_row == winner
    if same:
        assert candidate.kind == "stored_result"
        assert candidate.stored.result == r.ledger_row["result"]
    else:
        assert candidate.kind == "conflict" and candidate.boundary == "B3b"


@pytest.mark.parametrize("change", ["context", "runtime", "expired", "transaction"])
def test_zero_keeps_minimum_session_safety_before_reclassifying(
    rig, change, monkeypatch
):
    """lease失効は再掲するが、別handle/Session/topTXからの再掲にはしない。"""
    r = rig
    r.result = []
    r.candidates.append(_stored())
    if change == "context":
        r.after_execute = lambda: setattr(r.handle, "_bound_integrity_proof", object())
    elif change == "runtime":
        r.after_execute = lambda: tx._TRANSACTION_RUNTIMES.__setitem__(
            r.key, (r.session, ExitStack())
        )
    elif change == "expired":
        r.after_execute = lambda: setattr(r.handle, "_state_key", None)
    else:
        r.after_execute = lambda: monkeypatch.setattr(
            r.session, "get_transaction", lambda: None
        )
    with pytest.raises(RuntimeError):
        _call(r)
    assert len(r.classified) == 1 and r.results[0].closed


def test_real_source_control_loan_failure_cannot_be_replaced_by_business_values(
    rig, monkeypatch
):
    """事業側Session/nonceだけで本物control/RG1借用の失敗を成功化しない。"""
    r = rig
    monkeypatch.setattr(_E1CoreSource, "read", _REAL_SOURCE_READ)
    monkeypatch.setattr(_LiveWriterBinding, "assert_current", _REAL_BOUND_CURRENT)
    monkeypatch.delitem(tx._RG1_LOANS, r.key, raising=False)
    with pytest.raises(RuntimeError):
        _call(r)
    assert not r.calls


@pytest.mark.parametrize(
    "mutation",
    [
        "extra_parameter",
        "missing_parameter",
        "tenant_parameter",
        "kind_parameter",
        "json_bool_parameter",
        "json_extra_parameter",
        "json_mapping_subclass",
        "different_table",
        "different_constraint",
        "do_update",
        "different_returning",
        "extra_returning",
        "returning_boolean_type",
        "json_bind_type",
        "replacement_equal_bind",
        "extra_values",
        "plain_sql",
        "schema_option",
        "extra_option",
        "schema_value_subclass",
        "inline",
    ],
)
def test_factory_output_is_independently_rejected_before_session_execute(
    rig, monkeypatch, mutation
):
    """元prepare済みでもfactoryの別文/別型/別値をexecutorがSQL0で拒否する。"""
    from sqlalchemy import Boolean, Text, bindparam, column, literal_column, table, text
    from sqlalchemy.dialects.postgresql import insert

    r = rig
    factory = api._fixed_insert

    class _Dict(dict):
        pass

    class _String(str):
        pass

    def changed(token, tenant_id):
        statement, parameters = factory(token, tenant_id)
        parameters = dict(parameters)
        if mutation == "extra_parameter":
            parameters["unknown"] = True
        elif mutation == "missing_parameter":
            parameters.pop("reason")
        elif mutation == "tenant_parameter":
            parameters["tenant_id"] = uuid4()
        elif mutation == "kind_parameter":
            parameters["kind"] = "rejected"
        elif mutation == "json_bool_parameter":
            parameters["result"] = {**parameters["result"], "d3": True}
        elif mutation == "json_extra_parameter":
            parameters["result"] = {**parameters["result"], "unexpected": True}
        elif mutation == "json_mapping_subclass":
            parameters["result"] = _Dict(parameters["result"])
        elif mutation == "different_table":
            statement = insert(table("other", column("tenant_id"))).values(
                tenant_id=tenant_id
            )
        elif mutation in {"different_constraint", "do_update"}:
            original, _ = base._prepare_operation(token, tenant_id)
            assert isinstance(original, Insert) and original._values is not None
            statement = insert(original.table).values(dict(original._values))
            if mutation == "different_constraint":
                statement = statement.on_conflict_do_nothing(
                    constraint="uq_idempotency_ledger_kind"
                )
            else:
                statement = statement.on_conflict_do_update(
                    constraint="pk_idempotency_ledger", set_={"kind": "accepted"}
                )
            statement = statement.returning(literal_column("1")).execution_options(
                schema_translate_map={None: "public"}
            )
        elif mutation in {"different_returning", "extra_returning"}:
            statement = statement._generate()
            statement._returning = (
                (literal_column("2"),)
                if mutation == "different_returning"
                else (literal_column("1"), literal_column("1"))
            )
        elif mutation == "returning_boolean_type":
            statement = statement._generate()
            statement._returning = (literal_column("1", type_=Boolean()),)
        elif mutation == "json_bind_type":
            statement = statement.values(result=bindparam("result", type_=Text()))
        elif mutation == "replacement_equal_bind":
            statement = statement.values(
                kind=bindparam("kind", type_=statement.table.c.kind.type)
            )
        elif mutation == "extra_values":
            statement = statement.values(import_batch_id=None)
        elif mutation == "plain_sql":
            statement = text("DELETE FROM public.idempotency_ledger")
        elif mutation == "schema_option":
            statement = statement.execution_options(
                schema_translate_map={None: "other"}
            )
        elif mutation == "extra_option":
            statement = statement.execution_options(autocommit=True)
        elif mutation == "schema_value_subclass":
            statement = statement.execution_options(
                schema_translate_map={None: _String("public")}
            )
        else:
            statement = statement.inline()
        return statement, parameters

    monkeypatch.setattr(api, "_fixed_insert", changed)
    with pytest.raises(api.NativeLedgerInsertError):
        _call(r)
    assert not r.calls
