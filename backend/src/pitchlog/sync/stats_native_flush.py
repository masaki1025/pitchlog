"""真正native sourceの内側だけで同TX前値・唯一T5・固定Saveを直列実行する。"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from itertools import islice
from typing import Any, NamedTuple

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
    from pitchlog.repositories.stats_native_operations import (
        require_private_writer_call,
    )

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
    require_private_writer_call(
        "STATS_PRIMITIVES:read_writer_state",
        preflight,
        transaction.FUNCTION_OPERATION_REGISTRY,
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
        "decisions",
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
    require_private_writer_call(
        "STATS_PRIMITIVES:save_source", save, transaction.FUNCTION_OPERATION_REGISTRY
    )
    rows = _bounded_rows(scope.session.execute(save.statement, save.parameters))
    _assert_scope(scope, receipt, source)
    # 新Sは新canonical集合のhash。旧Sとの同値を求めず、前値はSaveのCASへ全値束縛する。
    decoded = decode_save_source_rows(rows, source_event_id=source.source_event_id)
    return TenantOperationResult(decoded)


_UNDO_RECEIPT_KEYS = frozenset(
    {
        "formatVersion",
        "profileSha256",
        "modelSha256",
        "tenantId",
        "gameId",
        "attemptId",
        "phaseId",
        "undoEventId",
        "targetEventId",
        "frameId",
        "frameDigest",
        "artifactSha256",
        "sourceFingerprint",
        "transactionId",
        "internalGeneration",
        "checkpointDigest",
        "oldFactVersionId",
        "factVersionId",
        "oldRevision",
        "revision",
        "beforeSourceSetSha256",
        "sourceSetSha256",
        "sourceCount",
    }
)


def _undo_selector_hash():
    """数学T5のhashとは独立した、唯一閉selectorのhashを読む。"""
    from pathlib import Path

    from pitchlog.domaingen.core import _canonical_hash
    from pitchlog.domaingen.pregen_checks import validate_undo_selection_profile

    path = Path(__file__).parents[3] / "domain/play-export-undo-selection.model.json"
    profile = json.loads(path.read_text())
    validate_undo_selection_profile(profile)
    return _canonical_hash(profile)


def _decode_undo_stats_receipt(raw):
    """有限text一行の全列を検査する。形だけで実行資格を発行しない。"""
    import re
    from uuid import UUID

    if type(raw) is not str or not 1 <= len(raw) <= 4096:
        raise StatsNativeFlushError

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise StatsNativeFlushError
            value[key] = item
        return value

    try:
        data = json.loads(raw, object_pairs_hook=unique)
        if (
            type(data) is not dict
            or set(data) != _UNDO_RECEIPT_KEYS
            or any(type(value) is not str for value in data.values())
            or data["formatVersion"] != "undo-native-stats-receipt-v1"
            or data["profileSha256"] != _undo_selector_hash()
            or data["modelSha256"] != SOURCE_MODEL_HASH
        ):
            raise StatsNativeFlushError
        for key in (
            "tenantId",
            "gameId",
            "attemptId",
            "phaseId",
            "undoEventId",
            "targetEventId",
            "frameId",
            "oldFactVersionId",
            "factVersionId",
        ):
            if str(UUID(data[key])) != data[key]:
                raise StatsNativeFlushError
        for key in (
            "frameDigest",
            "artifactSha256",
            "checkpointDigest",
            "beforeSourceSetSha256",
            "sourceSetSha256",
        ):
            if re.fullmatch(r"[a-f0-9]{64}", data[key]) is None:
                raise StatsNativeFlushError
        if (
            re.fullmatch(r"(?:wire-v1:)?[a-f0-9]{64}", data["sourceFingerprint"])
            is None
        ):
            raise StatsNativeFlushError
        for key in (
            "oldRevision",
            "revision",
            "sourceCount",
            "transactionId",
            "internalGeneration",
        ):
            if re.fullmatch(r"0|[1-9][0-9]{0,19}", data[key]) is None:
                raise StatsNativeFlushError
            limit = 2**64 if key == "transactionId" else 2**63
            if int(data[key]) >= limit:
                raise StatsNativeFlushError
        if (
            int(data["oldRevision"]) < 1
            or int(data["revision"]) != int(data["oldRevision"]) + 1
            or int(data["transactionId"]) < 1
            or int(data["internalGeneration"]) < 1
            or data["oldFactVersionId"] == data["factVersionId"]
            or data["undoEventId"] == data["targetEventId"]
        ):
            raise StatsNativeFlushError
    except (ValueError, TypeError, KeyError, OSError) as error:
        raise StatsNativeFlushError from error
    return data


@dataclass(frozen=True, slots=True, repr=False, init=False)
class _UndoStatsReceipt:
    """実bridgeの一回SQL結果と同実行stateだけが保持する貸与値。"""

    def __new__(cls, *args, **kwargs):
        """raw値から実SQL受領資格を構築しない。"""
        raise StatsNativeFlushError

    scope: _WriterScope
    execution: Any
    source: Any
    original: Any
    projected: Any
    raw: str
    preparation_json: str
    frame_id: Any
    frame_digest: str
    event_id: Any
    artifact: str


class _UndoStatsIssuance(NamedTuple):
    """receiptから独立した発行原本。tupleの全anchorは後発改変できない。"""

    receipt: _UndoStatsReceipt
    execution: Any
    raw: str
    receipt_values: tuple
    scope_values: tuple
    execution_anchor: tuple
    used: bool


_UNDO_STATS_ISSUED: dict[int, _UndoStatsIssuance] = {}


def _assert_undo_stats_issuance(state, *, used=False):
    """発行時objectと不変全anchorを独立registryから読み、clone/再刻印を拒否する。"""
    issued = _UNDO_STATS_ISSUED.get(id(state))
    if (
        type(issued) is not _UndoStatsIssuance
        or issued.execution is not state
        or issued.used is not used
        or state.stats_receipt is not issued.receipt
        or state.anchor is not issued.execution_anchor
    ):
        raise StatsNativeFlushError
    receipt = issued.receipt
    identity_fields = {"scope", "execution", "source", "original", "projected"}
    for field, original in zip(
        fields(_UndoStatsReceipt), issued.receipt_values, strict=True
    ):
        value = getattr(receipt, field.name)
        if field.name in identity_fields:
            if value is not original:
                raise StatsNativeFlushError
        elif type(value) is not type(original) or value != original:
            raise StatsNativeFlushError
    for field, original in zip(fields(_WriterScope), issued.scope_values, strict=True):
        value = getattr(receipt.scope, field.name)
        if field.name in {"nonce", "phase_snapshot"}:
            if type(value) is not type(original) or value != original:
                raise StatsNativeFlushError
        elif value is not original:
            raise StatsNativeFlushError
    return issued


def _close_undo_stats_receipt(state):
    """成功/故障/参照差替えでも当該実行の発行記録をfinallyで失効する。"""
    issued = _UNDO_STATS_ISSUED.get(id(state))
    if issued is not None and issued.execution is state:
        del _UNDO_STATS_ISSUED[id(state)]


def _bind_undo_stats_receipt(state, preparation, rows):
    """実consume後の同projection区間でだけ不変receiptを記録する。"""
    from pitchlog.domainrt.first_ball_projection import _canonical_json
    from pitchlog.sync.undo_execution import _execution_live

    _execution_live(state)
    if (
        state.phase != "consumed"
        or state.projected is None
        or state.projection_call is None
        or state.stats_receipt is not None
        or id(state) in _UNDO_STATS_ISSUED
        or type(rows) is not tuple
        or len(rows) != 1
        or type(rows[0]) is not tuple
        or len(rows[0]) != 1
    ):
        raise StatsNativeFlushError
    data = _decode_undo_stats_receipt(rows[0][0])
    scope = _capture_scope(state.handle, state.writer)
    expected = {
        "tenantId": str(scope.context.tenant_id),
        "gameId": str(state.event.game_id),
        "attemptId": str(scope.lease.attempt_id),
        "phaseId": str(scope.lease.phase_id),
        "undoEventId": str(state.event_id),
        "targetEventId": preparation["target"]["source"]["eventId"],
        "frameId": str(state.frame_id),
        "frameDigest": preparation["frame_digest"],
        "artifactSha256": state.artifact,
        "sourceFingerprint": preparation["source_fingerprint"],
        "checkpointDigest": preparation["after_source"]["checkpoint"]["ref"]["digest"],
        "transactionId": scope.bound._identity.transaction_id,
        "internalGeneration": str(
            json.loads(scope.phase_snapshot)["phase"]["internal_generation"]
        ),
    }
    if any(data[key] != value for key, value in expected.items()):
        raise StatsNativeFlushError
    receipt = object.__new__(_UndoStatsReceipt)
    for key, value in zip(
        (
            "scope",
            "execution",
            "source",
            "original",
            "projected",
            "raw",
            "preparation_json",
            "frame_id",
            "frame_digest",
            "event_id",
            "artifact",
        ),
        (
            scope,
            state,
            state.source,
            state.event,
            state.projected,
            rows[0][0],
            _canonical_json(preparation),
            state.frame_id,
            preparation["frame_digest"],
            state.event_id,
            state.artifact,
        ),
        strict=True,
    ):
        object.__setattr__(receipt, key, value)
    _UNDO_STATS_ISSUED[id(state)] = _UndoStatsIssuance(
        receipt,
        state,
        rows[0][0],
        tuple(getattr(receipt, field.name) for field in fields(_UndoStatsReceipt)),
        tuple(getattr(scope, field.name) for field in fields(_WriterScope)),
        state.anchor,
        False,
    )
    state.stats_receipt = receipt
    _assert_undo_stats_issuance(state)


def _flush_native_undo_stats(handle, writer, event, projected, *, generation):
    """同TXの真正投影/版更新receiptを一回だけ消費し、旧bool応答は拒否する。"""
    from pitchlog.sync.undo_execution import _EXECUTIONS, _execution_live

    state = _EXECUTIONS.get(getattr(handle, "_state_key", None))
    if state is None:
        raise StatsNativeFlushError
    issued = _assert_undo_stats_issuance(state)
    receipt = issued.receipt
    if state.source is not receipt.source:
        raise StatsNativeFlushError
    _execution_live(state)
    if (
        type(receipt) is not _UndoStatsReceipt
        or receipt.execution is not state
        or state.phase != "projected"
        or state.stats_flushed
        or state.event is not event
        or state.writer is not writer
        or receipt.original is not event
        or receipt.projected is not projected
        or state.completed_projected is not projected
        or receipt.scope.handle is not handle
        or receipt.scope.writer is not writer
        or receipt.frame_id != state.frame_id
        or receipt.event_id != state.event_id
        or receipt.artifact != state.artifact
        or type(generation) is not int
    ):
        raise StatsNativeFlushError
    _assert_scope(receipt.scope)
    _assert_undo_stats_issuance(state)
    data = _decode_undo_stats_receipt(issued.raw)
    if (
        generation != int(data["internalGeneration"])
        or data["frameDigest"] != receipt.frame_digest
        or data["undoEventId"] != str(state.event_id)
        or data["transactionId"] != receipt.scope.bound._identity.transaction_id
    ):
        raise StatsNativeFlushError
    # 保存SQL内でS/版更新を完了し、このhookは同実scopeの結果受領を不可分に確認する。
    # callerへraw値から新しい実行資格を作るfactoryは提供しない。
    _UNDO_STATS_ISSUED[id(state)] = issued._replace(used=True)
    state.stats_flushed = True
    _execution_live(state)
    _assert_scope(receipt.scope)
    _assert_undo_stats_issuance(state, used=True)
    return data
