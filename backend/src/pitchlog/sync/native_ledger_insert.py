"""真正nativeのaccepted台帳だけを同top-level TXへ閉挿入する。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import islice
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Integer, literal_column
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.postgresql.dml import Insert as PostgreSQLInsert
from sqlalchemy.dialects.postgresql.dml import OnConflictDoNothing
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Insert
from sqlalchemy.sql.elements import ColumnClause

from pitchlog.db.sync_protocol.models import IdempotencyLedger
from pitchlog.repositories import base, transaction
from pitchlog.repositories.context import TenantContext
from pitchlog.sync.control_provider.evidence import EventPhaseBinding
from pitchlog.sync.control_provider.writer_binding import (
    _LIVE_BINDINGS,
    _LiveWriterBinding,
)
from pitchlog.sync.first_ball_frame import FirstBallBridge, FirstBallFrame
from pitchlog.sync.idempotency import D5Candidate, D5Path, _json_value, classify_d5
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter
from pitchlog.sync.source_binding import _E1CoreSource
from pitchlog.sync.tokens import IdempotencyLedgerInsertToken

_COLUMNS = frozenset(
    {"tenant_id", "d5", "kind", "source_fingerprint", "result", "reason"}
)
_FIXED_SQL = (
    "INSERT INTO public.idempotency_ledger (d5, kind, source_fingerprint, result, "
    "reason, tenant_id) VALUES (%(d5)s::UUID, %(kind)s, %(source_fingerprint)s, "
    "%(result)s::JSONB, %(reason)s, %(tenant_id)s::UUID) ON CONFLICT ON CONSTRAINT "
    "pk_idempotency_ledger DO NOTHING RETURNING 1"
)


class NativeLedgerInsertError(RuntimeError):
    """原資格/入力/DB結果を表示しない私有経路の閉拒否。"""

    def __init__(self):
        """同TXと実挿入を値の成功申告へ置き換えない。"""
        super().__init__("native台帳の同一取引又は挿入結果が不一致です")


@dataclass(frozen=True, slots=True, repr=False)
class _Minimum:
    """再掲の前後に要求する実handle/Session/topTXだけを保持する。"""

    handle: Any
    key: object
    runtime: object
    session: Session
    context: TenantContext
    lifetime: tuple[object, object]


@dataclass(frozen=True, slots=True, repr=False)
class _Fresh:
    """実native準備とcontrol/business両側の元参照を保持する。"""

    minimum: _Minimum
    writer: PortWriter
    event: SyncEvent
    state: Any
    source: _E1CoreSource
    bound: _LiveWriterBinding
    lease: Any
    phase: EventPhaseBinding
    anchor: tuple[object, ...]
    nonce: bytes
    snapshot: str
    mode: str


def _minimum(handle, expected: _Minimum | None = None) -> _Minimum:
    """leaseのfresh検査を混ぜず、再掲にも必要な取引実体だけを照合する。"""
    if type(handle) is not transaction._TenantTransaction:
        raise NativeLedgerInsertError
    key = handle._state_key
    runtime = transaction._TRANSACTION_RUNTIMES.get(key)
    context = handle._context
    if (
        key is None
        or type(runtime) is not tuple
        or len(runtime) != 2
        or not isinstance(runtime[0], Session)
        or type(context) is not TenantContext
        or handle._bound_tenant_id != context.tenant_id
        or handle._bound_integrity_proof != context._integrity_proof
        or not context._has_valid_integrity_proof()
        or transaction._SYNC_APPLY_ACTIVE.get() is not True
        or transaction._port_phase(handle) is not None
        or key in transaction._INITIAL_ACTOR_STATES
        or key in transaction._STATS_READ_HANDLES
    ):
        raise NativeLedgerInsertError
    lifetime = handle._writer_lifetime()
    result = _Minimum(handle, key, runtime, runtime[0], context, lifetime)
    if expected is not None and (
        result.handle is not expected.handle
        or result.key is not expected.key
        or result.runtime is not expected.runtime
        or result.session is not expected.session
        or result.context is not expected.context
        or result.lifetime[0] is not expected.lifetime[0]
        or result.lifetime[1] is not expected.lifetime[1]
    ):
        raise NativeLedgerInsertError
    return result


def _json(value) -> str:
    """元wire/既typed payloadを同じJSON境界で比較し、計算を行わない。"""
    return json.dumps(
        _json_value(value), ensure_ascii=False, sort_keys=True, allow_nan=False
    )


def _unique_object(pairs):
    """resultの重複keyを辞書の後勝ちへ補修しない。"""
    result = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise NativeLedgerInsertError
        result[key] = value
    return result


def _bad_constant(value):
    """NaN等のJSON外値を受けない。"""
    raise NativeLedgerInsertError


def _check_token(token, event, fingerprint):
    """実prefixが作るaccepted1件の全値以外を私有INSERTへ渡さない。"""
    if (
        type(token) is not IdempotencyLedgerInsertToken
        or type(event) is not SyncEvent
        or type(event.d1) is not int
        or event.d1 <= 0
        or type(token.d5) is not UUID
        or token.d5 != UUID(event.d5)
        or type(token.kind) is not str
        or token.kind != "accepted"
        or type(token.source_fingerprint) is not str
        or token.source_fingerprint != fingerprint
        or token.reason is not None
        or type(token.result_json) is not str
    ):
        raise NativeLedgerInsertError
    try:
        value = json.loads(
            token.result_json,
            object_pairs_hook=_unique_object,
            parse_constant=_bad_constant,
        )
    except (ValueError, TypeError, RecursionError):
        raise NativeLedgerInsertError from None
    if (
        type(value) is not dict
        or set(value) != {"state", "d3", "temporary_id_mapping"}
        or type(value["state"]) is not str
        or value["state"] != "受理"
        or type(value["d3"]) is not int
        or value["d3"] != event.d1
        or type(value["temporary_id_mapping"]) is not dict
        or value["temporary_id_mapping"]
    ):
        raise NativeLedgerInsertError


def _fresh(minimum, writer, event, token, expected: _Fresh | None = None) -> _Fresh:
    """実ready frame/元source/nonce/借用を、挿入前と新規成功後だけ再確認する。"""
    from pitchlog.sync import first_ball_bridge as bridge
    from pitchlog.sync import first_ball_execution as first
    from pitchlog.sync import ordinary_pitch_execution as ordinary

    handle = minimum.handle
    _minimum(handle, minimum)
    from pitchlog.sync import lifecycle_execution as lifecycle
    from pitchlog.sync import undo_execution as undo

    if minimum.key in lifecycle._EXECUTIONS:
        if any(
            x.get(minimum.key) is not None
            for x in (first._EXECUTIONS, ordinary._EXECUTIONS, undo._EXECUTIONS)
        ):
            raise NativeLedgerInsertError
        return _fresh_lifecycle(minimum, writer, event, token, expected)
    if minimum.key in undo._EXECUTIONS:
        if (
            first._EXECUTIONS.get(minimum.key) is not None
            or ordinary._EXECUTIONS.get(minimum.key) is not None
        ):
            raise NativeLedgerInsertError
        return _fresh_undo(minimum, writer, event, token, expected)
    states = [
        state
        for state in (
            first._EXECUTIONS.get(minimum.key),
            ordinary._EXECUTIONS.get(minimum.key),
        )
        if state is not None
    ]
    if (
        len(states) != 1
        or type(event) is not SyncEvent
        or type(writer) is not PortWriter
    ):
        raise NativeLedgerInsertError
    state = states[0]
    if type(state) not in {first._Execution, ordinary._Execution}:
        raise NativeLedgerInsertError
    source = state.source
    if type(source) is not _E1CoreSource:
        raise NativeLedgerInsertError
    bound = source.bound
    phase = source.phase
    anchor = state.stats_source_reference
    if (
        state.handle is not handle
        or state.writer is not writer
        or state.event is not event
        or state.runtime is not minimum.runtime
        or type(state.phase) is not str
        or state.phase != "ready"
        or source.scope is not handle
        or source.context is not minimum.context
        or source.event is not event
        or source.write_started is not True
        or type(bound) is not _LiveWriterBinding
        or _LIVE_BINDINGS.get(minimum.key) is not bound
        or bound._handle is not handle
        or bound._used is not False
        or bound._owner[0] is not minimum.lifetime[0]
        or bound._owner[1] is not minimum.lifetime[1]
        or type(phase) is not EventPhaseBinding
        or phase.attempt.tenant_id != minimum.context.tenant_id
        or phase.attempt.game_id != UUID(event.game_id)
        or phase.d1 != event.d1
        or phase.d5 != UUID(event.d5)
        or type(anchor) is not tuple
        or len(anchor) != 8
        or type(bound._lease.nonce) is not bytes
        or len(bound._lease.nonce) != 32
        or bound._lease._phase_snapshot != bound._phase_snapshot
        or writer._active is not True
        or getattr(writer._execute, "__self__", None) is not handle
        or getattr(writer._execute, "__func__", None)
        is not transaction._TenantTransaction.run
        or state.payload is None
    ):
        raise NativeLedgerInsertError
    _check_token(token, event, phase.event_fingerprint)
    payload: Any
    if type(state) is first._Execution:
        mode = "first-ball-play-v1"
        if (
            type(state.bridge) is not FirstBallBridge
            or type(state.frame) is not FirstBallFrame
            or state.projected_event is not None
            or state.projection_call is not None
            or state.assigned_d2 is not None
            or anchor[0] is not state.bridge
            or anchor[1] is not state.frame
            or anchor[2] is not state.payload
        ):
            raise NativeLedgerInsertError
        first._live(state)
        value = bridge._read_ready_first_ball_frame(
            state.bridge, state.frame, writer=writer, event=event
        )
        if (
            value.tenant_id != minimum.context.tenant_id
            or value.game_id != UUID(event.game_id)
            or value.d5 != UUID(event.d5)
            or value.d1 != event.d1
            or value.generation != phase.attempt.internal_generation
            or value.source_fingerprint != phase.event_fingerprint
        ):
            raise NativeLedgerInsertError
        payload = state.payload.v7
        if _json(state.payload.v8.model_dump(mode="json", by_alias=True)) != _json(
            event.v8
        ):
            raise NativeLedgerInsertError
    elif type(state) is ordinary._Execution:
        mode = state.mode
        if (
            type(mode) is not str
            or mode
            not in {
                "ordinary-pitch-play-v1",
                "play-prefix-play-v2",
                "play-prefix-play-v3",
            }
            or type(state.frame) is not ordinary.OrdinaryPitchFrame
            or type(state.frame_id) is not UUID
            or state.projected is not None
            or state.projection_call is not None
            or state.preparation_used is not False
            or state.preparation_token is not None
            or state.preparation_digest is not None
            or state.prefix is None
            or anchor[0] is not state.frame
            or anchor[1] is not state.frame_id
            or anchor[2] is not state.payload
        ):
            raise NativeLedgerInsertError
        ordinary._live(state)
        payload = state.payload
        if (
            payload.calculation.request.rules
            != cast(Any, state.prefix).checkpoint.rules
        ):
            raise NativeLedgerInsertError
    else:
        raise NativeLedgerInsertError
    if (
        anchor[3] is not bound
        or anchor[4] is not bound._lease
        or anchor[5] is not phase
        or type(anchor[6]) is not bytes
        or anchor[6] != bound._lease.nonce
        or anchor[7] != bound._phase_snapshot
        or payload.format_version != mode
    ):
        raise NativeLedgerInsertError
    supplied = payload.model_dump(
        mode="json", by_alias=True, exclude_unset=mode != "first-ball-play-v1"
    )
    if _json(supplied) != _json(event.v7):
        raise NativeLedgerInsertError
    result = _Fresh(
        minimum,
        writer,
        event,
        state,
        source,
        bound,
        bound._lease,
        phase,
        anchor,
        bound._lease.nonce,
        bound._phase_snapshot,
        mode,
    )
    if expected is not None and (
        result.state is not expected.state
        or result.source is not expected.source
        or result.bound is not expected.bound
        or result.lease is not expected.lease
        or result.phase is not expected.phase
        or result.anchor is not expected.anchor
        or result.nonce != expected.nonce
        or result.snapshot != expected.snapshot
        or result.mode != expected.mode
    ):
        raise NativeLedgerInsertError
    _minimum(handle, minimum)
    return result


def _fresh_undo(minimum, writer, event, token, expected: _Fresh | None) -> _Fresh:
    """取消の実frameを再確認し、play用StatsStateやownD2を作らない。"""
    from pitchlog.sync import undo_execution as undo

    handle = minimum.handle
    _minimum(handle, minimum)
    state = undo._undo_native_ledger_state(handle, event, writer)
    if type(state) is not undo._Execution:
        raise NativeLedgerInsertError
    source = state.source
    if type(source) is not _E1CoreSource:
        raise NativeLedgerInsertError
    bound, phase, anchor = source.bound, source.phase, state.anchor
    if (
        state.handle is not handle
        or state.writer is not writer
        or state.event is not event
        or state.runtime is not minimum.runtime
        or state.phase != "ready"
        or source.scope is not handle
        or source.context is not minimum.context
        or source.event is not event
        or source.write_started is not True
        or type(bound) is not _LiveWriterBinding
        or _LIVE_BINDINGS.get(minimum.key) is not bound
        or bound._handle is not handle
        or bound._used is not False
        or bound._owner[0] is not minimum.lifetime[0]
        or bound._owner[1] is not minimum.lifetime[1]
        or type(phase) is not EventPhaseBinding
        or phase.attempt.tenant_id != minimum.context.tenant_id
        or phase.attempt.game_id != UUID(event.game_id)
        or phase.d1 != event.d1
        or phase.d5 != UUID(event.d5)
        or type(anchor) is not tuple
        or len(anchor) != 7
        or type(bound._lease.nonce) is not bytes
        or len(bound._lease.nonce) != 32
        or bound._lease._phase_snapshot != bound._phase_snapshot
        or type(writer) is not PortWriter
        or writer._active is not True
        or getattr(writer._execute, "__self__", None) is not handle
        or getattr(writer._execute, "__func__", None)
        is not transaction._TenantTransaction.run
        or type(state.frame) is not undo.UndoFrame
        or type(state.frame_id) is not UUID
        or type(state.event_id) is not UUID
        or state.prefix is None
        or state.projected is not None
        or state.projection_call is not None
        or type(state.payload) is not dict
        or state.payload.get("formatVersion") != "native-undo-prefix-v1"
        or _json(state.payload) != _json(event.v7)
        or event.v5 != "undo"
    ):
        raise NativeLedgerInsertError
    _check_token(token, event, phase.event_fingerprint)
    result = _Fresh(
        minimum,
        writer,
        event,
        state,
        source,
        bound,
        bound._lease,
        phase,
        anchor,
        bound._lease.nonce,
        bound._phase_snapshot,
        "native-undo-prefix-v1",
    )
    if expected is not None and (
        result.state is not expected.state
        or result.source is not expected.source
        or result.bound is not expected.bound
        or result.lease is not expected.lease
        or result.phase is not expected.phase
        or result.anchor is not expected.anchor
        or result.nonce != expected.nonce
        or result.snapshot != expected.snapshot
        or result.mode != expected.mode
    ):
        raise NativeLedgerInsertError
    _minimum(handle, minimum)
    return result


def _fresh_lifecycle(minimum, writer, event, token, expected: _Fresh | None) -> _Fresh:
    """終了再開の実frameを再確認し、play用StatsStateやownD2を作らない。"""
    from pitchlog.sync import lifecycle_execution as lifecycle

    handle = minimum.handle
    _minimum(handle, minimum)
    state = lifecycle._lifecycle_native_ledger_state(handle, event, writer)
    if type(state) is not lifecycle._Execution:
        raise NativeLedgerInsertError
    source = state.source
    if type(source) is not _E1CoreSource:
        raise NativeLedgerInsertError
    bound, phase, anchor = source.bound, source.phase, state.anchor
    if (
        state.handle is not handle
        or state.writer is not writer
        or state.event is not event
        or state.runtime is not minimum.runtime
        or state.phase != "ready"
        or source.scope is not handle
        or source.context is not minimum.context
        or source.event is not event
        or source.write_started is not True
        or type(bound) is not _LiveWriterBinding
        or _LIVE_BINDINGS.get(minimum.key) is not bound
        or bound._handle is not handle
        or bound._used is not False
        or bound._owner[0] is not minimum.lifetime[0]
        or bound._owner[1] is not minimum.lifetime[1]
        or type(phase) is not EventPhaseBinding
        or phase.attempt.tenant_id != minimum.context.tenant_id
        or phase.attempt.game_id != UUID(event.game_id)
        or phase.d1 != event.d1
        or phase.d5 != UUID(event.d5)
        or type(anchor) is not tuple
        or len(anchor) != 7
        or type(bound._lease.nonce) is not bytes
        or len(bound._lease.nonce) != 32
        or bound._lease._phase_snapshot != bound._phase_snapshot
        or type(writer) is not PortWriter
        or writer._active is not True
        or getattr(writer._execute, "__self__", None) is not handle
        or getattr(writer._execute, "__func__", None)
        is not transaction._TenantTransaction.run
        or type(state.frame) is not lifecycle.LifecycleFrame
        or type(state.frame_id) is not UUID
        or type(state.event_id) is not UUID
        or state.prefix is None
        or state.projected is not None
        or state.projection_call is not None
        or type(state.payload) is not dict
        or state.payload.get("formatVersion") != "native-game-lifecycle-v1"
        or _json(state.payload) != _json(event.v7)
        or event.v5 not in {"game_end_declaration", "game_reopen"}
    ):
        raise NativeLedgerInsertError
    _check_token(token, event, phase.event_fingerprint)
    result = _Fresh(
        minimum,
        writer,
        event,
        state,
        source,
        bound,
        bound._lease,
        phase,
        anchor,
        bound._lease.nonce,
        bound._phase_snapshot,
        "native-game-lifecycle-v1",
    )
    if expected is not None and (
        result.state is not expected.state
        or result.source is not expected.source
        or result.bound is not expected.bound
        or result.lease is not expected.lease
        or result.phase is not expected.phase
        or result.anchor is not expected.anchor
        or result.nonce != expected.nonce
        or result.snapshot != expected.snapshot
        or result.mode != expected.mode
    ):
        raise NativeLedgerInsertError
    _minimum(handle, minimum)
    return result


def _fixed_insert(token, tenant_id):
    """既plain INSERTを全検証した後、caller不可の単一拡張だけを構成する。"""
    spec = base._operation_spec(token)
    if spec.preflight is not None:
        raise NativeLedgerInsertError
    original, parameters = base._prepare_operation(token, tenant_id)
    if (
        type(original) is not Insert
        or original.table is not IdempotencyLedger.__table__
        or original._values is None
        or set(original._values) != _COLUMNS
        or set(parameters) != _COLUMNS
        or spec.capability_id != "CAP:idempotency_ledger:insert"
        or spec.token_type is not IdempotencyLedgerInsertToken
    ):
        raise NativeLedgerInsertError
    statement = (
        pg_insert(original.table)
        .values(dict(original._values))
        .on_conflict_do_nothing(constraint="pk_idempotency_ledger")
        .returning(literal_column("1", type_=Integer))
        .execution_options(schema_translate_map={None: "public"})
    )
    return statement, parameters


def _same_parameters(left, right) -> bool:
    """再prepare原値と全階層の型/値を照合し、bool/int等を同値化しない。"""
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return (
            all(type(key) is str for key in left)
            and all(type(key) is str for key in right)
            and left.keys() == right.keys()
            and all(_same_parameters(left[key], right[key]) for key in left)
        )
    if type(left) in {list, tuple}:
        return len(left) == len(right) and all(
            _same_parameters(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def _require_fixed_insert(statement, parameters, token, tenant_id) -> None:
    """factoryとは別に元登録を再読し、任意の文/型/値をSQL前に拒否する。"""
    spec = base._operation_spec(token)
    if spec.preflight is not None:
        raise NativeLedgerInsertError
    original, expected_parameters = base._prepare_operation(token, tenant_id)
    token_parameters = {
        "tenant_id": tenant_id,
        "d5": token.d5,
        "kind": token.kind,
        "source_fingerprint": token.source_fingerprint,
        "result": json.loads(
            token.result_json,
            object_pairs_hook=_unique_object,
            parse_constant=_bad_constant,
        ),
        "reason": token.reason,
    }
    if (
        spec.token_type is not IdempotencyLedgerInsertToken
        or spec.capability_id != "CAP:idempotency_ledger:insert"
        or not _same_parameters(expected_parameters, token_parameters)
    ):
        raise NativeLedgerInsertError
    if type(statement) is not PostgreSQLInsert:
        raise NativeLedgerInsertError
    conflict = statement._post_values_clause
    returned = statement._returning
    if (
        type(conflict) is not OnConflictDoNothing
        or conflict.constraint_target != "pk_idempotency_ledger"
        or conflict.inferred_target_elements is not None
        or conflict.inferred_target_whereclause is not None
        or type(returned) is not tuple
        or len(returned) != 1
        or type(returned[0]) is not ColumnClause
        or returned[0].name != "1"
        or returned[0].is_literal is not True
        or returned[0].table is not None
        or type(returned[0].type) is not Integer
    ):
        raise NativeLedgerInsertError
    options = statement.get_execution_options()
    schema_map = options.get("schema_translate_map")
    if (
        set(options) != {"schema_translate_map"}
        or type(schema_map) is not dict
        or list(schema_map) != [None]
        or type(schema_map[None]) is not str
        or schema_map[None] != "public"
    ):
        raise NativeLedgerInsertError
    if (
        type(original) is not Insert
        or type(statement) is not PostgreSQLInsert
        or original.table is not IdempotencyLedger.__table__
        or statement.table is not original.table
        or original._values is None
        or statement._values is None
        or set(original._values) != _COLUMNS
        or set(statement._values) != _COLUMNS
        or type(parameters) is not dict
        or set(parameters) != _COLUMNS
        or not _same_parameters(parameters, expected_parameters)
        or statement._inline
        or statement._return_defaults
        or statement._return_defaults_columns is not None
        or statement._sort_by_parameter_order
        or statement._with_options
        or statement._with_context_options
        or statement._propagate_attrs
        or statement._independent_ctes
        or statement._prefixes
        or statement._hints
        or statement.select is not None
        or statement._multi_values
    ):
        raise NativeLedgerInsertError
    # 元prepareのbindそのものだけを再使用する。等しい別JSON型/別bindを許さない。
    if any(
        statement._values[key] is not value for key, value in original._values.items()
    ):
        raise NativeLedgerInsertError
    try:
        actual_sql = str(
            statement.compile(
                dialect=postgresql.dialect(),
                schema_translate_map={None: "public"},
                render_schema_translate=True,
            )
        )
    except Exception:
        raise NativeLedgerInsertError from None
    if actual_sql != _FIXED_SQL:
        raise NativeLedgerInsertError


def _recheck_and_insert_native_result(
    handle, writer, event, token, path: D5Path
) -> D5Candidate | None:
    """旧再掲順を保ち、実新規1件だけtop-levelへ挿入する私有入口。"""
    minimum = _minimum(handle)
    if (
        type(token) is not IdempotencyLedgerInsertToken
        or type(token.d5) is not UUID
        or type(token.source_fingerprint) is not str
        or type(path) is not str
        or path not in {"P1", "P2"}
    ):
        raise NativeLedgerInsertError
    candidate = classify_d5(handle, token.d5, token.source_fingerprint, path)
    _minimum(handle, minimum)
    if candidate.kind != "unused":
        return candidate
    fresh = _fresh(minimum, writer, event, token)
    statement, parameters = _fixed_insert(token, minimum.context.tenant_id)
    _require_fixed_insert(statement, parameters, token, minimum.context.tenant_id)
    _fresh(minimum, writer, event, token, fresh)
    cursor = minimum.session.execute(statement, parameters)
    try:
        rows = list(islice(cursor, 2))
        if rows and (
            len(rows) != 1
            or (type(rows[0]) is not tuple and not isinstance(rows[0], Row))
            or len(rows[0]) != 1
            or type(rows[0][0]) is not int
            or rows[0][0] != 1
        ):
            raise NativeLedgerInsertError
    finally:
        cursor.close()
    # 待機中のlease失効をDI2より先に拒否しない。0件では取引実体だけを検査する。
    _minimum(handle, minimum)
    if rows:
        _fresh(minimum, writer, event, token, fresh)
        return None
    candidate = classify_d5(handle, token.d5, token.source_fingerprint, path)
    _minimum(handle, minimum)
    if candidate.kind == "unused":
        raise RuntimeError("D5 一意競合後に先着行を観測できない")
    return candidate
