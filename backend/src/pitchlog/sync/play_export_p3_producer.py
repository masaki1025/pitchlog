"""同じ実P3 frameの保存後に完成CSVだけを同TXへ書く候補。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from weakref import WeakKeyDictionary

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from pitchlog.exports.p3_projection import CorrectionResultReference, project_p3_direct
from pitchlog.exports.p3_snapshot import P3SnapshotIdentity
from pitchlog.exports.play_rows import PlayExportSupplyError
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.past_correction_execution import (
    p3_paged_ids,
    p3_paged_projection_candidate,
    p3_projection_candidate,
)
from pitchlog.sync.play_export_producer import PlayExportWriterUnavailable

_PRIOR = text(
    "SELECT * FROM stats_api.read_writer_p3_play_export_prior("
    ":attempt_id,:phase_id,:game_id,:capsule_id,:change_event_id,"
    ":binding_nonce,:checkpoint_id,:checkpoint_revision,:checkpoint_digest,:watermark)"
)
_READ = text(
    "SELECT * FROM stats_api.read_writer_p3_play_export_page("
    ":attempt_id,:phase_id,:game_id,:capsule_id,:change_event_id,"
    ":after_d1,:page_size,:binding_nonce,:prior_capsule_id,:prior_native_version_id,"
    ":prior_checkpoint_id,:prior_checkpoint_revision,:prior_checkpoint_digest)"
)
_SAVE = text(
    "SELECT * FROM stats_api.save_writer_p3_play_export_snapshot("
    ":attempt_id,:phase_id,:game_id,:capsule_id,:d1,:binding_nonce,"
    "CAST(:direct_json AS jsonb),:prior_capsule_id,:prior_native_version_id,"
    ":prior_checkpoint_id,:prior_checkpoint_revision,:prior_checkpoint_digest)"
)


@dataclass(frozen=True, slots=True, repr=False)
class _WriterContext:
    """実getterの値/identityを保持し、外部値をwriter資格へ昇格させない。"""

    source: Any
    game_id: UUID
    generation: int
    capsule_id: UUID
    change_event_id: UUID
    target_d1: int
    watermark: int
    attempt_id: UUID
    phase_id: UUID
    nonce: bytes
    transaction_id: str
    previous_checkpoint_id: UUID
    previous_checkpoint_revision: int
    previous_checkpoint_digest: str


class P3CsvPriorReceipt:
    """同一P3 frameの前版だけを保持する私有参照。自由生成不可。"""

    __slots__ = ("__weakref__",)

    def __new__(cls):
        """自由なsource値やboolからの発行を拒否する。"""
        raise PlayExportWriterUnavailable("P3 CSV前版receiptの自由生成不可")


@dataclass(slots=True, repr=False)
class _PriorState:
    scope: Any
    event: Any
    writer: Any
    context: _WriterContext
    prior_capsule_id: UUID | None
    prior_native_version_id: UUID
    prior_checkpoint_id: UUID
    prior_checkpoint_revision: int
    prior_checkpoint_digest: str
    used: bool = False


_PRIORS: WeakKeyDictionary[P3CsvPriorReceipt, _PriorState] = WeakKeyDictionary()


def prepare_p3_play_export_anchor(scope, event, writer) -> P3CsvPriorReceipt:
    """P3保存前のcurrent pointerを実readerから私有receiptへ固定する。"""
    context = _context(scope, event, writer)
    parameters = {
        **_parameters(context),
        "checkpoint_id": context.previous_checkpoint_id,
        "checkpoint_revision": context.previous_checkpoint_revision,
        "checkpoint_digest": context.previous_checkpoint_digest,
        "watermark": context.watermark,
    }
    if any(
        state.scope is scope and state.event is event
        for state in tuple(_PRIORS.values())
    ):
        raise PlayExportWriterUnavailable("P3 CSV前版receiptが二重発行")
    rows = tuple(scope.session.execute(_PRIOR, parameters).mappings())
    _same_context(scope, event, writer, context)
    required = {
        "prior_capsule_id",
        "prior_native_version_id",
        "prior_checkpoint_id",
        "prior_checkpoint_revision",
        "prior_checkpoint_digest",
        "transaction_id",
    }
    if len(rows) != 1 or set(rows[0]) != required:
        raise PlayExportWriterUnavailable("P3 CSV前版原本が一意でない")
    row = rows[0]
    if (
        row["prior_capsule_id"] is not None
        and type(row["prior_capsule_id"]) is not UUID
        or any(
            type(row[key]) is not UUID
            for key in ("prior_native_version_id", "prior_checkpoint_id")
        )
        or type(row["prior_checkpoint_revision"]) is not int
        or row["prior_checkpoint_revision"] < 1
        or type(row["prior_checkpoint_digest"]) is not str
        or re.fullmatch(r"[a-f0-9]{64}", row["prior_checkpoint_digest"]) is None
        or row["prior_checkpoint_id"] != context.previous_checkpoint_id
        or row["prior_checkpoint_revision"] != context.previous_checkpoint_revision
        or row["prior_checkpoint_digest"] != context.previous_checkpoint_digest
        or row["transaction_id"] != context.transaction_id
    ):
        raise PlayExportWriterUnavailable("P3 CSV前版原本の閉形が不正")
    receipt = object.__new__(P3CsvPriorReceipt)
    _PRIORS[receipt] = _PriorState(
        scope,
        event,
        writer,
        context,
        row["prior_capsule_id"],
        row["prior_native_version_id"],
        row["prior_checkpoint_id"],
        row["prior_checkpoint_revision"],
        row["prior_checkpoint_digest"],
    )
    return receipt


def _parameters(context: _WriterContext) -> dict:
    return {
        "attempt_id": context.attempt_id,
        "phase_id": context.phase_id,
        "game_id": context.game_id,
        "capsule_id": context.capsule_id,
        "change_event_id": context.change_event_id,
        "binding_nonce": context.nonce,
    }


def _consume_prior(scope, event, writer, receipt, context):
    state = _PRIORS.get(receipt) if type(receipt) is P3CsvPriorReceipt else None
    if (
        state is None
        or state.used
        or state.scope is not scope
        or state.event is not event
        or state.writer is not writer
        or state.context.source is not context.source
        or state.context != context
    ):
        raise PlayExportWriterUnavailable("P3 CSV前版receiptが別frame又は消費済")
    state.used = True
    return state


def _context(scope, event, writer) -> _WriterContext:
    """任意callbackやsuccess boolでなく、既実execution getterだけを使う。"""
    if type(scope) is not _TenantTransaction or type(event) is not SyncEvent:
        raise PlayExportWriterUnavailable("P3 CSVの実frameが不成立")
    paged = p3_paged_projection_candidate(scope, event, writer)
    if paged is None:
        capsule, _, source = p3_projection_candidate(scope, event, writer)
        capsule_id, change = capsule.capsule_id, capsule.change_event_id
        checkpoint = capsule.previous_checkpoint
        generation, target, watermark = (
            capsule.internal_generation,
            capsule.target_d1,
            len(capsule.items),
        )
    else:
        proof, source = paged
        capsule_id, change = p3_paged_ids(scope, event, writer)
        checkpoint = proof.checkpoint
        generation, target, watermark = (
            proof.internal_generation,
            proof.target.d1,
            proof.watermark,
        )
    source.read(scope, event)
    lease = source.bound._lease
    return _WriterContext(
        source,
        UUID(event.game_id),
        generation,
        capsule_id,
        change,
        target,
        watermark,
        lease.attempt_id,
        lease.phase_id,
        lease.nonce,
        source.bound._identity.transaction_id,
        UUID(checkpoint.id),
        int(checkpoint.revision),
        checkpoint.content_digest,
    )


def _same_context(scope, event, writer, expected: _WriterContext) -> None:
    """頁/書込の前後で元lease/frame/取引の全値を再確認する。"""
    actual = _context(scope, event, writer)
    if actual.source is not expected.source or actual != expected:
        raise PlayExportWriterUnavailable("P3 CSVの実frameが変化")


def _persist_p3_play_exports(scope, event, writer, receipt: P3CsvPriorReceipt) -> None:
    """自由JSONを受けず、真正reader→既projector→固定保存関数へ一度写す。

    正式helper/登録と共有P3保存後hookはrootが供給する。未配置の例外を
    成功へ置換しない。旧通常writerのplay_input/xmin条件は変更しない。
    """
    context = _context(scope, event, writer)
    prior = _consume_prior(scope, event, writer, receipt, context)
    after = 0
    saved = 0
    expected_version = None
    while after < context.watermark:
        _same_context(scope, event, writer, context)
        parameters = {
            **_parameters(context),
            "after_d1": after,
            "page_size": 25,
            "prior_capsule_id": prior.prior_capsule_id,
            "prior_native_version_id": prior.prior_native_version_id,
            "prior_checkpoint_id": prior.prior_checkpoint_id,
            "prior_checkpoint_revision": prior.prior_checkpoint_revision,
            "prior_checkpoint_digest": prior.prior_checkpoint_digest,
        }
        if after < context.target_d1 - 1:
            # 不変prefixの88列をPythonへ読まず、同じ25件S頁をDB内でcarryする。
            result = tuple(
                scope.session.execute(
                    _SAVE, {**parameters, "d1": after + 1, "direct_json": None}
                )
            )
            _same_context(scope, event, writer, context)
            expected_count = min(25, context.target_d1 - after - 1)
            if len(result) != expected_count:
                raise PlayExportWriterUnavailable("P3 CSV先行carry頁が不足")
            seen = set()
            for offset, row in enumerate(result, 1):
                if (
                    len(row) != 2
                    or type(row[0]) is not UUID
                    or type(row[1]) is not int
                    or row[1] != after + offset
                    or row[0] in seen
                ):
                    raise PlayExportWriterUnavailable("P3 CSV先行carry receipt不一致")
                seen.add(row[0])
            after += expected_count
            saved += expected_count
            continue
        rows = tuple(scope.session.execute(_READ, parameters).mappings())
        if not 1 <= len(rows) <= 25:
            raise PlayExportWriterUnavailable("P3 CSV原本頁が未供給")
        for row in rows:
            _same_context(scope, event, writer, context)
            # reader返却JSONは私有関数内で実cap/S/同xidへ結ばれる。自由入力ではない。
            expected = P3SnapshotIdentity(
                context.source.context.tenant_id,
                context.game_id,
                context.generation,
                context.capsule_id,
                row["d1"],
                row["original_play_row_id"],
                row["source_event_id"],
                row["play_row_id"],
                row["play_row_version"],
                row["item_digest"],
                row["capsule_source_set_digest"],
                row["capsule_stats_version_id"],
            )
            version = (
                row["fact_version_id"],
                row["revision"],
                row["source_set_sha256"],
                row["source_count"],
                row["completion_state"],
            )
            if expected_version is None:
                expected_version = version
            if (
                version != expected_version
                or row["transaction_id"] != context.transaction_id
                or expected.d1 != after + 1
                or row["target_d1"] != context.target_d1
                or row["watermark"] != context.watermark
                or row["source_count"] != context.watermark
                or row["original_snapshot_source_event_id"] != row["original_event_id"]
                or row["original_snapshot_play_version"]
                != row["original_play_row"]["version"]
                or row["original_snapshot_generation"] != context.generation
                or row["original_snapshot_sequence"] != row["d2"]
            ):
                raise PlayExportWriterUnavailable("P3 CSV原本の全版が不一致")
            item = {
                key: row[key]
                for key in (
                    "d1",
                    "d2",
                    "state",
                    "original_payload",
                    "original_history_entry",
                    "original_play_row",
                    "original_play_runners",
                    "payload",
                    "history_entry",
                    "play_row",
                    "play_runners",
                )
            }
            item.update(
                original_event_id=str(row["original_event_id"]),
                effective_event_id=str(expected.effective_event_id),
                original_play_row_id=str(expected.original_play_row_id),
                effective_play_row_id=str(expected.effective_play_row_id),
                digest=expected.item_digest,
            )
            direct = None
            if expected.d1 >= context.target_d1:
                reference = None
                if expected.d1 == context.target_d1:
                    reference = CorrectionResultReference(
                        context.source.context.tenant_id,
                        context.game_id,
                        context.capsule_id,
                        expected.effective_event_id,
                        row["reference_id"],
                        row["replacement_key"],
                        row["replacement_label"],
                        row["reference_captured_at"],
                    )
                direct = project_p3_direct(
                    row["original_csv_json"],
                    item,
                    expected,
                    target_d1=context.target_d1,
                    reference=reference,
                )
            result = tuple(
                scope.session.execute(
                    _SAVE,
                    {
                        **parameters,
                        "d1": expected.d1,
                        "direct_json": None
                        if direct is None
                        else json.dumps(
                            direct,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        ),
                    },
                )
            )
            _same_context(scope, event, writer, context)
            if len(result) != 1 or tuple(result[0]) != (
                expected.effective_play_row_id,
                expected.d1,
            ):
                raise PlayExportWriterUnavailable("P3 CSV保存receiptが不一致")
            after = expected.d1
            saved += 1
    if saved != context.watermark:
        raise PlayExportSupplyError("P3 CSV完成集合が不足")
    _same_context(scope, event, writer, context)


def persist_p3_play_exports(scope, event, writer, receipt: P3CsvPriorReceipt) -> None:
    """source不足を利用者内容拒否へ誤分類せず同TXの非成功にする。"""
    try:
        _persist_p3_play_exports(scope, event, writer, receipt)
    except (
        PlayExportSupplyError,
        SQLAlchemyError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise PlayExportWriterUnavailable("P3毎球CSVの同TX保存原本が未供給") from error
