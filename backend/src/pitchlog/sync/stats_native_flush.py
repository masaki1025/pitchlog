"""真正native sourceの内側だけで同TX前値・唯一T5・固定Saveを直列実行する。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import islice
from typing import Any

from sqlalchemy.orm import Session

from pitchlog.repositories import transaction
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.stats_function_codec import (
    build_save_source_call,
    build_writer_state_call,
    decode_save_source_rows,
    decode_writer_state_rows,
)
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.stats.facts import SavePrimitiveSourceToken, prepare_native_evaluation
from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH
from pitchlog.sync import stats_native_hook as native
from pitchlog.sync.control_provider.writer_binding import (
    _LIVE_BINDINGS,
    _LiveWriterBinding,
)
from pitchlog.sync.ports import PortWriter


class StatsNativeFlushError(RuntimeError):
    """原資格や評価原本を例外文へ含めない閉拒否。"""

    def __init__(self):
        """結果不明/失効を保存成功や0へ補完しない。"""
        super().__init__("成績native同TX保存の資格又は結果が不一致です")


@dataclass(frozen=True, slots=True, repr=False)
class _WriterScope:
    """私有入口で実registryから採った参照。SQLを外部から受けない。"""

    handle: Any
    writer: PortWriter
    key: object
    runtime: object
    session: Session
    lifetime: tuple[object, object]
    context: TenantContext
    bound: _LiveWriterBinding
    lease: Any
    nonce: bytes
    phase_snapshot: str


def _capture_scope(handle, writer) -> _WriterScope:
    """同期中の真正writerと登録Session以外ではSQLへ進まない。"""
    if type(handle) is not transaction._TenantTransaction:
        raise StatsNativeFlushError
    key = handle._state_key
    runtime = transaction._TRANSACTION_RUNTIMES.get(key)
    bound = _LIVE_BINDINGS.get(key)
    if (
        key is None
        or type(runtime) is not tuple
        or len(runtime) != 2
        or not isinstance(runtime[0], Session)
        or type(bound) is not _LiveWriterBinding
        or type(writer) is not PortWriter
    ):
        raise StatsNativeFlushError
    scope = _WriterScope(
        handle,
        writer,
        key,
        runtime,
        runtime[0],
        handle._writer_lifetime(),
        handle._context,
        bound,
        bound._lease,
        bound._lease.nonce,
        bound._phase_snapshot,
    )
    _assert_scope(scope)
    return scope


def _assert_scope(scope, receipt=None, source=None) -> None:
    """両SQLの前後で同Session/TX/生存frame/全原本を再確認する。"""
    handle = scope.handle
    if (
        type(handle) is not transaction._TenantTransaction
        or handle._state_key is not scope.key
        or transaction._TRANSACTION_RUNTIMES.get(scope.key) is not scope.runtime
        or scope.runtime[0] is not scope.session
        or transaction._SYNC_APPLY_ACTIVE.get() is not True
        or transaction._port_phase(handle) is not None
        or scope.key in transaction._STATS_READ_HANDLES
        or scope.key in transaction._INITIAL_ACTOR_STATES
        or type(scope.context) is not TenantContext
        or handle._context is not scope.context
        or handle._bound_tenant_id != scope.context.tenant_id
        or handle._bound_integrity_proof != scope.context._integrity_proof
        or not scope.context._has_valid_integrity_proof()
        or scope.writer._active is not True
        or getattr(scope.writer._execute, "__self__", None) is not handle
        or getattr(scope.writer._execute, "__func__", None)
        is not transaction._TenantTransaction.run
        or _LIVE_BINDINGS.get(scope.key) is not scope.bound
        or scope.bound._handle is not handle
        or scope.bound._used
        or scope.bound._lease is not scope.lease
        or type(scope.nonce) is not bytes
        or len(scope.nonce) != 32
        or scope.lease.nonce != scope.nonce
        or scope.bound._phase_snapshot != scope.phase_snapshot
        or scope.lease._phase_snapshot != scope.phase_snapshot
    ):
        raise StatsNativeFlushError
    handle._assert_writer_lifetime(scope.lifetime)
    current = handle._writer_lifetime()
    if current[0] is not scope.lifetime[0] or current[1] is not scope.lifetime[1]:
        raise StatsNativeFlushError
    scope.bound.assert_current()
    if receipt is None and source is None:
        return
    if type(receipt) is not native.NativeStatsSourceReceipt:
        raise StatsNativeFlushError
    issued = native._RECEIPTS.get(receipt)
    if (
        issued is None
        or issued.used is not True
        or issued.handle is not handle
        or issued.writer is not scope.writer
        or issued.state_key is not scope.key
        or issued.bound is not scope.bound
        or issued.lease is not scope.lease
        or issued.nonce != scope.nonce
        or type(source) is not native._NativeStatsSource
        or source != issued.values
    ):
        raise StatsNativeFlushError
    state, anchor, event_row, ledger_row, observed = native._read_values(
        handle,
        scope.writer,
        issued.event,
        issued.projected,
        issued.generation,
    )
    if (
        state is not issued.execution
        or len(anchor) != 9
        or anchor[-1] is not receipt
        or any(a is not b for a, b in zip(anchor[:8], issued.anchor, strict=True))
        or not native._same_wire_value(event_row, issued.event_row)
        or not native._same_wire_value(ledger_row, issued.ledger_row)
        or observed != source
        or source.tenant_id != scope.context.tenant_id
        or source.attempt_id != scope.lease.attempt_id
        or source.phase_id != scope.lease.phase_id
        or source.game_id != scope.lease.game_id
        or source.binding_nonce != scope.nonce
    ):
        raise StatsNativeFlushError


def _bounded_rows(result) -> tuple[tuple[object, ...], ...]:
    """1行契約の上限+1だけを取得し、未知の全件を読まない。"""
    try:
        return tuple(tuple(row) for row in islice(result, 2))
    finally:
        result.close()


def _flush_native_stats(handle, writer, event, projected, *, generation):
    """同TXの真正sourceからのみ成績を保存し、例外は外TXへ伝播する。"""
    scope = _capture_scope(handle, writer)
    receipt = native._issue_native_stats_source(
        handle,
        writer,
        event,
        projected,
        generation=generation,
    )
    source = native._consume_native_stats_source(handle, receipt)
    _assert_scope(scope, receipt, source)
    preflight = build_writer_state_call(
        source.attempt_id,
        source.phase_id,
        source.source_event_id,
        SOURCE_MODEL_HASH,
        binding_nonce=scope.nonce,
    )
    # この私有入口の2固定factoryだけがSQLを形成する。caller SQLや汎用tokenは受けない。
    _assert_scope(scope, receipt, source)
    before_rows = _bounded_rows(
        scope.session.execute(preflight.statement, preflight.parameters)
    )
    _assert_scope(scope, receipt, source)
    revision, old_source_set = decode_writer_state_rows(before_rows)[0]
    prepared = prepare_native_evaluation(
        json.loads(source.native_payload_json),
        attempt_id=source.attempt_id,
        phase_id=source.phase_id,
        source_event_id=source.source_event_id,
        expected_revision=revision,
        expected_source_set_sha256=old_source_set,
    )
    expected = {
        "attempt_id": source.attempt_id,
        "phase_id": source.phase_id,
        "source_event_id": source.source_event_id,
        "model_sha256": SOURCE_MODEL_HASH,
        "expected_revision": revision,
        "expected_source_set_sha256": old_source_set,
    }
    if type(prepared) is not SavePrimitiveSourceToken or any(
        not native._same_wire_value(getattr(prepared, key), value)
        for key, value in expected.items()
    ):
        raise StatsNativeFlushError
    evaluation = json.loads(prepared.evaluation_json)
    if type(evaluation) is not dict or set(evaluation) != {
        "metrics",
        "pa_row",
        "pending",
        "selected",
        "source_event_id",
    }:
        raise StatsNativeFlushError
    evaluation["native_rule_sha256"] = source.native_rule_sha256
    evaluation_json = json.dumps(
        evaluation,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    save = build_save_source_call(
        source.attempt_id,
        source.phase_id,
        source.source_event_id,
        SOURCE_MODEL_HASH,
        revision,
        old_source_set,
        evaluation_json,
        binding_nonce=scope.nonce,
    )
    _assert_scope(scope, receipt, source)
    rows = _bounded_rows(scope.session.execute(save.statement, save.parameters))
    _assert_scope(scope, receipt, source)
    # 新Sは新canonical集合のhash。旧Sとの同値を求めず、前値はSaveのCASへ全値束縛する。
    decoded = decode_save_source_rows(rows, source_event_id=source.source_event_id)
    return TenantOperationResult(decoded)
