"""同期要求の公開サービス入口とイベント単位 ACK を組み立てる。

認証と wire 形式は HTTP 入口の責務とし、ここでは発行済み TenantContext と
S-1 の SyncRequest を受ける。保存処理は P1〜P5 の局所経路を再利用する。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast
from uuid import UUID

from pitchlog.db.recording_rights.models import RecordingGeneration
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.transaction import (
    _sync_apply_active,
    tenant_transaction_scope,
)
from pitchlog.sync import port_guard
from pitchlog.sync.change_path import apply_p3_change
from pitchlog.sync.crash_points import reach
from pitchlog.sync.gate import RG1Blocked, game_accessible, gated_writer
from pitchlog.sync.idempotency import (
    D5Candidate,
    classify_request_d5,
    operation_fingerprint,
)
from pitchlog.sync.model import (
    A5Result,
    AckResult,
    ChangeResult,
    SyncEvent,
    SyncRequest,
)
from pitchlog.sync.ordering import apply_p2_event
from pitchlog.sync.ports import (
    ContentValidationPort,
    ProjectionPort,
    RecordingRightsPort,
)
from pitchlog.sync.prefix_path import (
    P1ContentRejection,
    P1PreconditionError,
    P1Result,
    P1Target,
    PlayerRegistration,
    _cell,
    apply_p1_event,
)
from pitchlog.sync.rejection import (
    RejectionPath,
    RejectionResult,
    apply_rejection_or_escrow,
    content_reason_for_precondition,
)
from pitchlog.sync.tokens import RecordingGenerationReadToken

type ApplyResult = AckResult | ChangeResult | Literal["B6", "B7"]
type D1Result = P1Result | RejectionResult

_GENERATION_COLUMNS = tuple(RecordingGeneration.__table__.c.keys())


@dataclass(frozen=True, slots=True)
class _BatchPreflight:
    """④の内部候補と、⑤より前に読んだ D3 を外部確定まで保持する。"""

    d3: int
    candidates: tuple[D5Candidate, ...]
    has_recording_right: bool


def _preflight_d1(
    context: TenantContext,
    request: SyncRequest,
    rights: RecordingRightsPort,
    registrations: Mapping[str, PlayerRegistration],
) -> _BatchPreflight:
    """③-a、全件の④、未使用候補の⑤を先に行い、結果はまだ返さない。"""
    with tenant_transaction_scope(context) as scope:
        with _sync_apply_active():
            with gated_writer(scope, rights) as gated:
                fingerprints = tuple(
                    operation_fingerprint(
                        event, request.path, registrations.get(event.d5)
                    )
                    for event in request.events
                )
                candidates = classify_request_d5(scope, request, fingerprints)
                rows = scope.run(
                    RecordingGenerationReadToken(UUID(request.game_id))
                ).rows
                if len(rows) != 1:
                    raise RuntimeError("自テナントの記録権世代行が一件ではない")
                d3 = _cell(rows[0], _GENERATION_COLUMNS, "confirmed_watermark")
                if type(d3) is not int:
                    raise RuntimeError("D3 の型が不正")
                has_right = True
                if any(candidate.kind == "unused" for candidate in candidates):
                    port_guard.require_registered_port(rights)
                    has_right = rights.holds_recording_right(
                        request.game_id, request.d4, request.v12, gated.writer
                    )
                return _BatchPreflight(d3, candidates, has_right)


def _run_d1_event(
    context: TenantContext,
    request: SyncRequest,
    event: SyncEvent,
    rights: RecordingRightsPort,
    projection: ProjectionPort,
    validator: ContentValidationPort,
    registration: PlayerRegistration | None,
    target: P1Target | None,
) -> D1Result:
    """一件の局所経路を実行し、⑦の拒否を T9、⑤の不成立を T8 へ渡す。"""
    reach("before_transaction")
    try:
        if request.path == "P4":
            outcome: D1Result = apply_rejection_or_escrow(
                context, event, rights, request.v12, path="P4", reason=None
            )
        elif request.path == "P2":
            outcome = apply_p2_event(
                context, event, rights, projection, validator, request.v12
            )
        else:
            outcome = apply_p1_event(
                context,
                event,
                rights,
                projection,
                validator,
                request.v12,
                registration=registration,
                target=target,
            )
    except P1PreconditionError as error:
        if error.category == "recording_rights":
            outcome = apply_rejection_or_escrow(
                context,
                event,
                rights,
                request.v12,
                path=cast(RejectionPath, request.path),
                reason=None,
                registration=registration,
            )
        elif error.category == "w2_violation" or isinstance(error, P1ContentRejection):
            outcome = apply_rejection_or_escrow(
                context,
                event,
                rights,
                request.v12,
                path=cast(RejectionPath, request.path),
                reason=content_reason_for_precondition(error),
                cause=(
                    "w2_violation"
                    if error.category == "w2_violation"
                    else "content_rejection"
                ),
                registration=registration,
            )
        else:
            raise
    reach("after_transaction")
    return outcome


def _event_state(result: D1Result) -> Literal["受理", "重複", "拒否", "退避", "未処理"]:
    """局所結果を A5 の一件分へ変換する。"""
    if isinstance(result, RejectionResult):
        return result.state
    if result.accepted:
        return "重複" if result.replayed else "受理"
    if result.a5 is not None:
        return result.a5
    if result.boundary in ("B3", "B3a", "B3b"):
        return "拒否"
    if result.boundary == "B4":
        return "退避"
    return "未処理"


def _escrow_without_right(
    context: TenantContext,
    request: SyncRequest,
    event: SyncEvent,
    rights: RecordingRightsPort,
    registration: PlayerRegistration | None,
) -> RejectionResult:
    """⑤で不成立の未使用 D5 を P4/T8 の一取引へ渡す。"""
    reach("before_transaction")
    result = apply_rejection_or_escrow(
        context,
        event,
        rights,
        request.v12,
        path=cast(RejectionPath, request.path),
        reason=None,
        registration=registration,
    )
    reach("after_transaction")
    return result


def apply_sync_request(
    context: TenantContext,
    request: SyncRequest,
    rights: RecordingRightsPort,
    projection: ProjectionPort,
    validator: ContentValidationPort,
    *,
    registrations: Mapping[str, PlayerRegistration] | None = None,
    targets: Mapping[str, P1Target] | None = None,
) -> ApplyResult:
    """③以降を経路へ渡し、D1 昇順の A5 と唯一の停止境界を確定する。

    B5・B11 は認証を所有する HTTP 入口が判定する。B6・B7 は ACK を
    持たないためコードだけを返し、P3 は専用の独立結果を返す。
    """
    if request.path == "P3":
        reach("before_transaction")
        result = apply_p3_change(context, request, rights, projection, validator)
        reach("after_transaction")
        return result

    # ③は RG1 と D5 より前。存在しない試合と他テナントの試合を同じ B6 にする。
    if not game_accessible(context, UUID(request.game_id), tenant_transaction_scope):
        return "B6"
    registrations = registrations or {}
    targets = targets or {}
    try:
        preflight = _preflight_d1(context, request, rights, registrations)
    except RG1Blocked:
        return "B7"
    if (
        request.path == "P4"
        and preflight.has_recording_right
        and any(candidate.kind == "unused" for candidate in preflight.candidates)
    ):
        raise P1PreconditionError("P4 は記録権不成立の経路に限る", "other")

    events = sorted(request.events, key=lambda item: item.d1 or 0)
    candidates = {
        event.d5: candidate
        for event, candidate in zip(request.events, preflight.candidates, strict=True)
    }
    a5: list[A5Result] = []
    mappings: dict[str, str] = {}
    d3 = preflight.d3
    boundary: Literal["B1", "B2", "B3", "B4"] = "B1"
    b3_branch: Literal["B3a", "B3b", "O4"] | None = None
    reason: str | None = None
    stopped = False

    for event in events:
        assert event.d1 is not None and event.d4 is not None
        if stopped:
            a5.append(A5Result(event.d4, event.d1, event.d5, "未処理"))
            continue
        registration = registrations[event.d5] if event.d5 in registrations else None
        target = targets[event.d5] if event.d5 in targets else None
        if not preflight.has_recording_right:
            if candidates[event.d5].kind != "unused":
                a5.append(A5Result(event.d4, event.d1, event.d5, "未処理"))
                continue
            result: D1Result = _escrow_without_right(
                context,
                request,
                event,
                rights,
                registration,
            )
        else:
            result = _run_d1_event(
                context,
                request,
                event,
                rights,
                projection,
                validator,
                registration,
                target,
            )
        if result.boundary in ("B6", "B7"):
            return result.boundary
        state = _event_state(result)
        event_reason = result.reason or (
            "同じ D5 の内容が異なる" if result.boundary == "B3b" else None
        )
        a5.append(A5Result(event.d4, event.d1, event.d5, state, event_reason))
        if isinstance(result, P1Result) and result.accepted:
            d3 = max(d3, result.d3)
        for temporary, permanent in (
            result.temporary_id_mapping if isinstance(result, P1Result) else ()
        ):
            if temporary in mappings and mappings[temporary] != permanent:
                raise RuntimeError("同じ一時 ID に異なる確定選手 ID がある")
            mappings[temporary] = permanent
        if result.boundary == "B2":
            boundary = "B2"
            stopped = True
        elif result.boundary in ("B3", "B3a", "B3b"):
            boundary = "B3"
            b3_branch = "O4" if result.boundary == "B3" else result.boundary
            reason = event_reason
            stopped = True
        elif result.boundary == "B4":
            boundary = "B4"
            stopped = True

    return AckResult(boundary, d3, tuple(a5), b3_branch, reason, mappings)
