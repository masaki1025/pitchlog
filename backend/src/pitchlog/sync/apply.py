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
from pitchlog.db.sync_protocol.models import RejectedEventOriginal
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.transaction import (
    _sync_apply_active,
    _TenantTransaction,
    tenant_transaction_scope,
)
from pitchlog.sync import port_guard
from pitchlog.sync.change_path import apply_p3_change
from pitchlog.sync.crash_points import reach
from pitchlog.sync.gate import RG1Blocked, game_accessible, gated_writer
from pitchlog.sync.idempotency import (
    D5Candidate,
    classify_request_d5,
    classify_result,
    operation_fingerprint,
)
from pitchlog.sync.model import (
    A5Rejection,
    A5Result,
    AckResult,
    B3Branch,
    ChangeResult,
    SyncEvent,
    SyncEventBatch,
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
from pitchlog.sync.routing import EventPath, route_for_event
from pitchlog.sync.tokens import (
    IdempotencyLedgerReadToken,
    RecordingGenerationByNumberReadToken,
    RecordingGenerationReadToken,
    RejectedOriginalReadToken,
)

type ApplyResult = AckResult | ChangeResult | Literal["B6", "B7"]
type D1Result = P1Result | RejectionResult

_GENERATION_COLUMNS = tuple(RecordingGeneration.__table__.c.keys())
_REJECTION_COLUMNS = tuple(RejectedEventOriginal.__table__.c.keys())


def _needs_original_path(event: SyncEvent) -> bool:
    """墓標を優先し、改訂版だけが T9 の経路を必要とする。"""
    return (
        isinstance(event.v9, Mapping)
        and event.v9.get("tombstone") is not True
        and event.v9.get("revision") is True
    )


@dataclass(frozen=True, slots=True)
class _BatchPreflight:
    """④の内部候補と、⑤より前に読んだ D3 を外部確定まで保持する。"""

    d3: int
    candidates: tuple[D5Candidate, ...]
    has_recording_right: bool
    current_generation: int
    # 要求の D4 が指す世代の D3。現世代の要求では d3 と同じ(省略時も同じ)。
    request_d3: int | None = None
    paths: Mapping[int, EventPath] | None = None


def _batch_paths(
    scope: _TenantTransaction, events: tuple[SyncEvent, ...]
) -> dict[int, EventPath]:
    """指紋より先に、改訂版の不変な拒否原本から経路を確定する。"""
    paths: dict[int, EventPath] = {}
    for event in events:
        assert event.d1 is not None
        original_path: EventPath | None = None
        if _needs_original_path(event):
            assert isinstance(event.v9, Mapping)
            raw_d5 = event.v9.get("rejected_d5")
            try:
                original_d5 = UUID(raw_d5) if type(raw_d5) is str else None
            except ValueError:
                original_d5 = None
            if original_d5 is not None and str(original_d5) == raw_d5:
                rows = scope.run(RejectedOriginalReadToken(original_d5)).rows
                if len(rows) == 1:
                    original = _cell(rows[0], _REJECTION_COLUMNS, "payload")
                    if isinstance(original, Mapping):
                        saved = original.get("path")
                        if saved in ("P1", "P2"):
                            original_path = cast(EventPath, saved)
                        else:
                            # 旧原本には経路がない。元の V5/V9 から参加区分を復元する。
                            old_event = SyncEvent(
                                event.d5,
                                event.game_id,
                                v5=original.get("event_kind"),
                                v9=original.get("replacement_state"),
                            )
                            original_path = route_for_event(old_event)
        # 原本が読めない改訂版は自身の V5・V9 で判定する。後で原本が読めて
        # 判定が変わっても、保存済み D5 は台帳の指紋で照合し直す(_preflight_d1)。
        paths[event.d1] = route_for_event(event, original_path)
    return paths


def _preflight_d1(
    context: TenantContext,
    request: SyncRequest,
    rights: RecordingRightsPort,
    registrations: Mapping[int, PlayerRegistration],
    batch: SyncEventBatch | None = None,
) -> _BatchPreflight:
    """③-a、全件の④、未使用候補の⑤を先に行い、結果はまだ返さない。"""
    with tenant_transaction_scope(context) as scope:
        with _sync_apply_active():
            with gated_writer(scope, rights) as gated:
                paths = (
                    _batch_paths(scope, request.events) if batch is not None else None
                )
                if paths is None:
                    fingerprints = tuple(
                        operation_fingerprint(
                            event, request.path, registrations.get(event.d1)
                        )
                        for event in request.events
                    )
                    candidates = classify_request_d5(scope, request, fingerprints)
                else:
                    resolved: list[D5Candidate] = []
                    for event in request.events:
                        assert event.d1 is not None
                        path = paths[event.d1]
                        registration = registrations.get(event.d1)
                        ledger = scope.run(IdempotencyLedgerReadToken(UUID(event.d5)))
                        candidate = classify_result(
                            ledger,
                            operation_fingerprint(event, path, registration),
                            path,
                        )
                        if _needs_original_path(event) and candidate.kind == "conflict":
                            # 改訂版の経路は原本の可視性で変わりうる。保存済み D5 は
                            # 台帳の不変な指紋と一致する経路を優先し、再掲を保つ。
                            other: EventPath = "P2" if path == "P1" else "P1"
                            alternative = classify_result(
                                ledger,
                                operation_fingerprint(event, other, registration),
                                other,
                            )
                            if alternative.kind == "stored_result":
                                paths[event.d1] = other
                                candidate = alternative
                        resolved.append(candidate)
                    candidates = tuple(resolved)
                rows = scope.run(
                    RecordingGenerationReadToken(UUID(request.game_id))
                ).rows
                if len(rows) != 1:
                    raise RuntimeError("自テナントの記録権世代行が一件ではない")
                d3 = _cell(rows[0], _GENERATION_COLUMNS, "confirmed_watermark")
                if type(d3) is not int:
                    raise RuntimeError("D3 の型が不正")
                generation = _cell(rows[0], _GENERATION_COLUMNS, "generation")
                if type(generation) is not int:
                    raise RuntimeError("記録権世代の型が不正")
                # D3 は (試合, D4) ごと(SP 6-1 R1)。旧 D4 の要求の ACK は、その世代の
                # D3 を起点にして後退させない(R4)。D4 の整数表現は退避の世代番号と
                # 同じ規則で照合し、読めない・行がない D4 は現世代の D3 のままにする。
                request_d3 = d3
                if (
                    request.d4 is not None
                    and request.d4.isdecimal()
                    and request.d4 != str(generation)
                ):
                    request_rows = scope.run(
                        RecordingGenerationByNumberReadToken(
                            UUID(request.game_id), int(request.d4)
                        )
                    ).rows
                    if len(request_rows) == 1:
                        value = _cell(
                            request_rows[0], _GENERATION_COLUMNS, "confirmed_watermark"
                        )
                        if type(value) is not int:
                            raise RuntimeError("D3 の型が不正")
                        request_d3 = value
                has_right = True
                if any(candidate.kind == "unused" for candidate in candidates):
                    port_guard.require_registered_port(rights)
                    has_right = rights.holds_recording_right(
                        request.game_id, request.d4, request.v12, gated.writer
                    )
                return _BatchPreflight(
                    d3, candidates, has_right, generation, request_d3, paths
                )


def _run_d1_event(
    context: TenantContext,
    request: SyncRequest,
    event: SyncEvent,
    rights: RecordingRightsPort,
    projection: ProjectionPort,
    validator: ContentValidationPort,
    registration: PlayerRegistration | None,
    target: P1Target | None,
    *,
    path: RejectionPath | None = None,
) -> D1Result:
    """一件の局所経路を実行し、⑦の拒否を T9、⑤の不成立を T8 へ渡す。"""
    reach("before_transaction")
    path = cast(RejectionPath, request.path) if path is None else path
    try:
        if path == "P4":
            outcome: D1Result = apply_rejection_or_escrow(
                context, event, rights, request.v12, path="P4", reason=None
            )
        elif path == "P2":
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
                path=path,
                reason=None,
                registration=registration,
            )
        elif error.category == "w2_violation" or isinstance(error, P1ContentRejection):
            outcome = apply_rejection_or_escrow(
                context,
                event,
                rights,
                request.v12,
                path=path,
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
    *,
    path: RejectionPath | None = None,
) -> RejectionResult:
    """⑤で不成立の未使用 D5 を P4/T8 の一取引へ渡す。"""
    reach("before_transaction")
    result = apply_rejection_or_escrow(
        context,
        event,
        rights,
        request.v12,
        path=cast(RejectionPath, request.path if path is None else path),
        reason=None,
        registration=registration,
    )
    reach("after_transaction")
    return result


def _replay_existing(
    context: TenantContext,
    request: SyncRequest,
    event: SyncEvent,
    rights: RecordingRightsPort,
    projection: ProjectionPort,
    validator: ContentValidationPort,
    registration: PlayerRegistration | None,
    target: P1Target | None,
    *,
    path: RejectionPath | None = None,
) -> D1Result:
    """⑤ 不成立の要求で、既存 D5 の保存済み結果(または B3b)を再掲する。

    P1・P2 の局所経路は ④ の D5 分類で再掲・B3b を決め、⑤ には進まない。
    P4 の要求は、退避を書いた P4 の経路(P4 の指紋)で照合して再掲する。
    """
    reach("before_transaction")
    path = cast(RejectionPath, request.path) if path is None else path
    if path == "P4":
        # P4 の退避は P4 の指紋で保存されているので、同じ経路で照合・再掲する。
        outcome: D1Result = apply_rejection_or_escrow(
            context,
            event,
            rights,
            request.v12,
            path="P4",
            reason=None,
            registration=registration,
        )
    elif path == "P2":
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
    reach("after_transaction")
    return outcome


def _b3_branch(result: D1Result) -> B3Branch:
    """B3 の分岐を局所結果から決める。区分なしの B3 は O4・O5 の理由種別で分ける。"""
    if result.boundary == "B3":
        # 区分なしの B3 を返すのは prefix_path の O4・O5 だけ(どちらも b3_code を持つ)。
        assert isinstance(result, P1Result) and result.b3_code is not None
        return result.b3_code
    assert result.boundary in ("B3a", "B3b")
    return result.boundary


def _a5_rejection(result: D1Result, reason: str | None) -> A5Rejection:
    """A5「拒否」1 件の B3 の分岐を局所結果から決める(US-1 提示 4-3)。

    境界の値に依らず、A5 が「拒否」の件には必ず分岐を付ける。B4 の要求で
    保存済みの B3a を再掲した件も同じ規則で内容起因 B3a になる。

    Args:
        result: 「拒否」に写した局所結果。
        reason: A5 に載せる理由の文言。

    Returns:
        内容起因(B3a・B3b)・O4・O5 のいずれかの分岐と理由。理由と分岐の
        組の検査は ``A5Rejection`` が行う。
    """
    branch = _b3_branch(result)
    if branch == "B3a" or branch == "B3b":
        return A5Rejection("内容起因", branch, cast(str, reason))
    return A5Rejection(branch, None, cast(str, reason))


def _is_replay(result: D1Result) -> bool:
    """保存済み結果の再掲かを返す。"""
    return result.replayed


def apply_sync_request(
    context: TenantContext,
    request: SyncRequest,
    rights: RecordingRightsPort,
    projection: ProjectionPort,
    validator: ContentValidationPort,
    *,
    registrations: Mapping[int, PlayerRegistration] | None = None,
    targets: Mapping[int, P1Target] | None = None,
) -> ApplyResult:
    """③以降を経路へ渡し、D1 昇順の A5 と唯一の停止境界を確定する。

    B5・B11 は認証を所有する HTTP 入口が判定する。B6・B7 は ACK を
    持たないためコードだけを返し、P3 は専用の独立結果を返す。
    登録値と解決済み対象は、同じ D5 を持つ別イベントを区別するため D1 で引く。
    """
    if request.path == "P3":
        reach("before_transaction")
        result = apply_p3_change(context, request, rights, projection, validator)
        reach("after_transaction")
        return result
    return _apply_d1_request(
        context,
        request,
        rights,
        projection,
        validator,
        registrations=registrations,
        targets=targets,
    )


def apply_sync_events(
    context: TenantContext,
    batch: SyncEventBatch,
    rights: RecordingRightsPort,
    projection: ProjectionPort,
    validator: ContentValidationPort,
    *,
    registrations: Mapping[int, PlayerRegistration] | None = None,
    targets: Mapping[int, P1Target] | None = None,
) -> AckResult | Literal["B6", "B7"]:
    """E-1 の各イベントの経路を判定し、単一の ACK を確定する。"""
    # 内部の共通ループには P1 の要求形を渡す。局所経路は④で D1 ごとに確定する。
    request = SyncRequest("P1", batch.game_id, batch.events, d4=batch.d4, v12=batch.v12)
    return _apply_d1_request(
        context,
        request,
        rights,
        projection,
        validator,
        registrations=registrations,
        targets=targets,
        batch=batch,
    )


def _apply_d1_request(
    context: TenantContext,
    request: SyncRequest,
    rights: RecordingRightsPort,
    projection: ProjectionPort,
    validator: ContentValidationPort,
    *,
    registrations: Mapping[int, PlayerRegistration] | None = None,
    targets: Mapping[int, P1Target] | None = None,
    batch: SyncEventBatch | None = None,
) -> AckResult | Literal["B6", "B7"]:
    """両公開口の D1 昇順・部分成功・停止境界を一か所で確定する。"""
    # ③は RG1 と D5 より前。存在しない試合と他テナントの試合を同じ B6 にする。
    if not game_accessible(context, UUID(request.game_id), tenant_transaction_scope):
        return "B6"
    registrations = registrations or {}
    targets = targets or {}
    if any(
        type(key) is not int for mapping in (registrations, targets) for key in mapping
    ):
        raise TypeError("registrations と targets は D1 をキーにする")
    try:
        preflight = (
            _preflight_d1(context, request, rights, registrations)
            if batch is None
            else _preflight_d1(context, request, rights, registrations, batch)
        )
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
        event.d1: candidate
        for event, candidate in zip(request.events, preflight.candidates, strict=True)
    }
    a5: list[A5Result] = []
    mappings: dict[str, str] = {}
    d3 = preflight.d3 if preflight.request_d3 is None else preflight.request_d3
    boundary: Literal["B1", "B2", "B3", "B4"] = "B1"
    b3_branch: B3Branch | None = None
    reason: str | None = None
    stopped = False
    # ⑥ の走査位置。D3 + 1 から始め、要求の中で処理した D1 の次へ進める
    # (欠落 = 要求の中で番号が欠けていること。D3 を進めない再掲の次を欠落にしない)。
    next_d1 = d3 + 1
    if not preflight.has_recording_right:
        # ⑤ は要求単位の判定で、⑥ の停止規則(DI5)の射程外(SP 6-2・B4)。
        # 保存済み結果は再掲、未使用 D5 は T8、異内容候補は未処理にする。
        boundary = "B4"

    for event in events:
        assert event.d1 is not None and event.d4 is not None
        if stopped:
            a5.append(A5Result(event.d4, event.d1, event.d5, "未処理"))
            continue
        registration = registrations.get(event.d1)
        target = targets.get(event.d1)
        path = preflight.paths[event.d1] if preflight.paths is not None else None
        if not preflight.has_recording_right:
            if candidates[event.d1].kind == "conflict":
                # ⑤ の B4 では ⑥ に進まない。異内容候補は拒否原本を作らず未処理。
                a5.append(A5Result(event.d4, event.d1, event.d5, "未処理"))
                continue
            if candidates[event.d1].kind == "unused":
                result: D1Result = (
                    _escrow_without_right(context, request, event, rights, registration)
                    if path is None
                    else _escrow_without_right(
                        context, request, event, rights, registration, path=path
                    )
                )
            else:
                result = (
                    _replay_existing(
                        context,
                        request,
                        event,
                        rights,
                        projection,
                        validator,
                        registration,
                        target,
                    )
                    if path is None
                    else _replay_existing(
                        context,
                        request,
                        event,
                        rights,
                        projection,
                        validator,
                        registration,
                        target,
                        path=path,
                    )
                )
        elif event.d1 > next_d1:
            # ⑥: D3 + 1 から D1 昇順に走査し、欠落があればその位置で B2。
            # ④ の候補の種類(既存 D5・B3b・保存済みの退避)によらず、欠落より
            # 後ろは外部結果として確定しない(SP 6-2 の ⑥・6-3)。
            a5.append(A5Result(event.d4, event.d1, event.d5, "未処理"))
            boundary = "B2"
            stopped = True
            continue
        else:
            result = (
                _run_d1_event(
                    context,
                    request,
                    event,
                    rights,
                    projection,
                    validator,
                    registration,
                    target,
                )
                if path is None
                else _run_d1_event(
                    context,
                    request,
                    event,
                    rights,
                    projection,
                    validator,
                    registration,
                    target,
                    path=path,
                )
            )
        if result.boundary in ("B6", "B7"):
            return result.boundary
        next_d1 = max(next_d1, event.d1 + 1)
        state = _event_state(result)
        event_reason = result.reason or (
            "同じ D5 の内容が異なる" if result.boundary == "B3b" else None
        )
        rejection = _a5_rejection(result, event_reason) if state == "拒否" else None
        a5.append(
            A5Result(event.d4, event.d1, event.d5, state, event_reason, rejection)
        )
        if isinstance(result, P1Result) and result.accepted:
            d3 = max(d3, result.d3)
        for temporary, permanent in (
            result.temporary_id_mapping if isinstance(result, P1Result) else ()
        ):
            if temporary in mappings and mappings[temporary] != permanent:
                raise RuntimeError("同じ一時 ID に異なる確定選手 ID がある")
            mappings[temporary] = permanent
        if not preflight.has_recording_right:
            # B4 の要求では境界は ⑤ で決まっている。各件は A5 にだけ写す。
            continue
        if _is_replay(result) and state == "退避":
            # 退避の再掲は境界結果を決めない(SP 変更履歴 U-14)。B4 専用の文面を
            # V12 が一致する要求へ流用しない(SP 6-3 の B4)。
            continue
        if result.boundary == "B2":
            boundary = "B2"
            stopped = True
        elif result.boundary in ("B3", "B3a", "B3b"):
            boundary = "B3"
            b3_branch = _b3_branch(result)
            reason = event_reason
            stopped = True
        elif result.boundary == "B4":
            boundary = "B4"
            stopped = True

    return AckResult(boundary, d3, tuple(a5), b3_branch, reason, mappings)
