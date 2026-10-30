"""D1 付きイベントの内容拒否 T9 と記録権不一致の退避 T8 を確定する。

認可は公開入口が先に検査する。RG1 はこの経路の前後で検査し、
試合行、記録権世代行の順でロックした同じトランザクションに原本と結果を保存する。
"""

from __future__ import annotations

import json
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.transaction import (
    _sync_apply_active,
    _TenantTransaction,
    tenant_transaction_scope,
)
from pitchlog.sync import port_guard
from pitchlog.sync.crash_points import reach
from pitchlog.sync.gate import RG1Blocked, game_accessible, gated_writer
from pitchlog.sync.idempotency import (
    D5Candidate,
    _json_value,
    classify_d5,
    decode_stored_negative,
    event_source,
    recheck_and_insert_result,
)
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter, RecordingRightsPort
from pitchlog.sync.prefix_path import (
    P1ContentRejection,
    P1PreconditionError,
    PlayerRegistration,
    _lock_game_generation,
)
from pitchlog.sync.tokens import (
    EvacuatedOriginalInsertToken,
    IdempotencyLedgerInsertToken,
    RejectedOriginalInsertToken,
)

type RejectionPath = Literal["P1", "P2", "P4"]
type RejectionBoundary = Literal["B2", "B3a", "B3b", "B4", "B6", "B7"]


@dataclass(frozen=True, slots=True)
class RejectionResult:
    """一イベントの拒否・退避結果。要求全体の ACK は後段が組み立てる。"""

    boundary: RejectionBoundary
    d3: int
    state: Literal["拒否", "退避", "未処理"]
    reason: str | None = None
    replayed: bool = False


class _RaceReplay(RuntimeError):
    """D5 の先着確定を見た後、ポートの書き込みを戻して結果を運ぶ。"""

    def __init__(self, result: RejectionResult) -> None:
        """先着の保存済み結果または B3b を保持する。"""
        self.result = result


def content_reason_for_precondition(error: P1PreconditionError) -> str:
    """W2 違反と内容検証失敗だけを B3a/T9 の理由へ写す。

    記録権不成立は B4、その他の前提違反は各段階の境界へ渡す。
    """
    if error.category != "w2_violation" and not isinstance(error, P1ContentRejection):
        raise ValueError("内容拒否以外を T9 に記録できない")
    return str(error)


def _candidate_result(candidate: D5Candidate, d3: int) -> RejectionResult | None:
    """同じ D5 の再掲と、異内容 B3b を新しい原本なしで決める。"""
    if candidate.kind == "conflict":
        return RejectionResult("B3b", d3, "拒否", "同じ D5 の内容が異なる")
    if candidate.kind == "unused":
        return None
    stored = candidate.stored
    if stored is None:
        raise RuntimeError("拒否・退避以外の保存済み結果は元の適用経路で再掲する")
    negative = decode_stored_negative(stored)
    return RejectionResult(
        negative.boundary,
        negative.d3,
        negative.state,
        negative.reason,
        True,
    )


def _original(event: SyncEvent, fingerprint: str) -> str:
    """W2 の対象照合に必要な原本と、D5 の指紋を同じ行に残す。"""
    source = event_source(event)
    source["operation_fingerprint"] = fingerprint
    return json.dumps(_json_value(source), ensure_ascii=False, sort_keys=True)


def _commit_result(
    scope: _TenantTransaction,
    event: SyncEvent,
    fingerprint: str,
    d3: int,
    *,
    path: RejectionPath,
    kind: Literal["rejected", "evacuated"],
    reason: str | None = None,
    old_generation: int | None = None,
) -> RejectionResult:
    """台帳と対応する原本を一つの T 要素として確定する。"""
    from pitchlog.sync.prefix_path import _LEGACY_LOCKED_SOURCE

    return _commit_result_in_scope(
        scope,
        event,
        fingerprint,
        d3,
        source=_LEGACY_LOCKED_SOURCE,
        path=path,
        kind=kind,
        reason=reason,
        old_generation=old_generation,
    )


def _commit_result_in_scope(
    scope: _TenantTransaction,
    event: SyncEvent,
    fingerprint: str,
    d3: int,
    *,
    source: object,
    path: RejectionPath,
    kind: Literal["rejected", "evacuated"],
    reason: str | None = None,
    old_generation: int | None = None,
) -> RejectionResult:
    """台帳と対応する原本を一つの T 要素として確定する。"""
    from pitchlog.sync.prefix_path import _LEGACY_LOCKED_SOURCE
    from pitchlog.sync.source_binding import SourceBindingError, _E1CoreSource

    if source is _LEGACY_LOCKED_SOURCE:
        original_json = _original(event, fingerprint)
    elif type(source) is _E1CoreSource:
        selected = source.read(scope, event)
        if (
            selected.event_fingerprint != fingerprint
            or selected.wire_original_json is None
        ):
            raise SourceBindingError("E1原本と台帳指紋が不一致")
        original_json = selected.wire_original_json
        source.begin_write(scope, event)
    else:
        raise SourceBindingError("E1拒否sourceが不正")
    d5 = UUID(event.d5)
    state: Literal["拒否", "退避"] = "拒否" if kind == "rejected" else "退避"
    token = IdempotencyLedgerInsertToken(
        d5,
        kind,
        fingerprint,
        json.dumps({"state": state, "d3": d3}, ensure_ascii=False),
        reason,
    )
    raced = recheck_and_insert_result(scope, token, path)
    if raced is not None:
        result = _candidate_result(raced, d3)
        if result is None:
            raise RuntimeError("D5 再照合が未使用に戻った")
        raise _RaceReplay(result)
    reach("after_t9_ledger" if kind == "rejected" else "after_t8_ledger")
    if kind == "rejected":
        scope.run(RejectedOriginalInsertToken(uuid4(), d5, original_json))
        reach("after_t9_original")
    else:
        if old_generation is None or event.d1 is None:
            raise RuntimeError("退避原本の世代または D1 がない")
        scope.run(
            EvacuatedOriginalInsertToken(
                uuid4(),
                UUID(event.game_id),
                old_generation,
                event.d1,
                d5,
                original_json,
            )
        )
        reach("after_t8_original")
    return RejectionResult("B3a" if kind == "rejected" else "B4", d3, state, reason)


def _apply_locked(
    scope: _TenantTransaction,
    event: SyncEvent,
    rights: RecordingRightsPort,
    v12: object,
    path: RejectionPath,
    registration: PlayerRegistration | None,
    reason: str | None,
    cause: Literal["content_rejection", "w2_violation"],
    writer: PortWriter,
) -> RejectionResult:
    """DI1〜DI4 を守り、未使用 D5 だけを現在の記録権へ進める。"""
    from pitchlog.sync.prefix_path import _LEGACY_LOCKED_SOURCE

    return _apply_rejection_in_scope(
        scope,
        event,
        rights,
        v12,
        path,
        registration,
        reason,
        cause,
        writer,
        source=_LEGACY_LOCKED_SOURCE,
    )


def _apply_rejection_in_scope(
    scope: _TenantTransaction,
    event: SyncEvent,
    rights: RecordingRightsPort,
    v12: object,
    path: RejectionPath,
    registration: PlayerRegistration | None,
    reason: str | None,
    cause: Literal["content_rejection", "w2_violation"],
    writer: PortWriter,
    *,
    source: object,
) -> RejectionResult:
    """DI1〜DI4 を守り、未使用 D5 だけを現在の記録権へ進める。"""
    locked = _lock_game_generation(scope, UUID(event.game_id))
    if locked is None:
        raise RuntimeError("認可後に試合行が消失した")
    _, d3 = locked
    from pitchlog.repositories.transaction import _port_predecision_phase
    from pitchlog.sync.prefix_path import (
        _LEGACY_LOCKED_SOURCE,
        _locked_source_fingerprint,
    )

    fingerprint = _locked_source_fingerprint(scope, event, path, registration, source)
    candidate = classify_d5(scope, UUID(event.d5), fingerprint, path)
    previous = _candidate_result(candidate, d3)
    if previous is not None:
        return previous

    if type(event.d1) is not int or event.d1 <= 0 or not event.d4:
        raise P1PreconditionError("D1 付き経路には D1 と D4 が必要")
    port_guard.require_registered_port(rights)
    with (
        nullcontext()
        if source is _LEGACY_LOCKED_SOURCE
        else _port_predecision_phase(scope, "rights")
    ):
        has_right = rights.holds_recording_right(event.game_id, event.d4, v12, writer)

    if not has_right:
        # DB の old_generation は bigint。D4 の整数表現がない要求を推測しない。
        from pitchlog.sync.prefix_path import _LEGACY_LOCKED_SOURCE
        from pitchlog.sync.source_binding import _E1CoreSource

        if source is _LEGACY_LOCKED_SOURCE:
            try:
                old_generation = int(event.d4)
            except ValueError as error:
                raise P1PreconditionError("退避する旧 D4 の世代番号が不正") from error
            if old_generation <= 0 or str(old_generation) != event.d4:
                raise P1PreconditionError("退避する旧 D4 の世代番号が不正")
        elif type(source) is _E1CoreSource:
            source.read(scope, event)
            old_generation = source.phase.attempt.internal_generation
            if type(old_generation) is not int or not 0 < old_generation < 2**63:
                raise P1PreconditionError("退避する旧 D4 の世代番号が不正")
        else:
            raise P1PreconditionError("退避する旧 D4 の世代番号が不正")
        return _commit_result_in_scope(
            scope,
            event,
            fingerprint,
            d3,
            source=source,
            path=path,
            kind="evacuated",
            old_generation=old_generation,
        )
    if reason is None:
        raise P1PreconditionError("記録権が成立するイベントは内容拒否の理由が必要")
    if event.d1 > d3 + 1:
        return RejectionResult("B2", d3, "未処理")
    if event.d1 <= d3 and cause != "w2_violation":
        raise P1PreconditionError("確定済み D1 は内容拒否原本にできない")
    if not reason:
        raise P1PreconditionError("内容拒否の理由が空")
    return _commit_result_in_scope(
        scope,
        event,
        fingerprint,
        d3,
        source=source,
        path=path,
        kind="rejected",
        reason=reason,
    )


def apply_rejection_or_escrow(
    context: TenantContext,
    event: SyncEvent,
    rights: RecordingRightsPort,
    v12: object,
    *,
    path: RejectionPath,
    reason: str | None,
    cause: Literal["content_rejection", "w2_violation"] = "content_rejection",
    registration: PlayerRegistration | None = None,
) -> RejectionResult:
    """P5/T9 または P4/T8 を一イベントのトランザクションで確定する。

    Args:
        context: 認可済み試合のテナント文脈。
        event: S-1 を満たす原本。
        rights: U-R1 が所有する記録権判定ポート。
        v12: 要求レベルの証明。
        path: 入力が通った D1 付き経路。
        reason: 内容拒否の理由。記録権不一致では使わない。
        cause: W2 の対象違反では確定済み D1 にも拒否原本を残す。
        registration: P1 のその場登録に伴う原本値。

    Returns:
        B3a・B3b・B4 などの局所結果。ACK は公開入口が組み立てる。
    """
    if path == "P4" and registration is not None:
        raise ValueError("P4 はその場登録を持たない")
    if not game_accessible(context, UUID(event.game_id), tenant_transaction_scope):
        return RejectionResult("B6", 0, "未処理")
    try:
        with tenant_transaction_scope(context) as scope:
            with _sync_apply_active():
                with gated_writer(scope, rights) as gated:
                    result = _apply_locked(
                        scope,
                        event,
                        rights,
                        v12,
                        path,
                        registration,
                        reason,
                        cause,
                        gated.writer,
                    )
                    if result.boundary in ("B3a", "B4") and not result.replayed:
                        gated.mark_written()
                    return result
    except RG1Blocked:
        return RejectionResult("B7", 0, "未処理")
    except _RaceReplay as replay:
        return replay.result
