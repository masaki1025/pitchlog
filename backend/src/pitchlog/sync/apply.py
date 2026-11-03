"""同期要求の公開サービス入口とイベント単位 ACK を組み立てる。

認証と wire 形式は HTTP 入口の責務とし、ここでは発行済み TenantContext と
S-1 の SyncRequest を受ける。保存処理は P1〜P5 の局所経路を再利用する。
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Literal, cast
from uuid import UUID

from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.transaction import (
    _sync_apply_active,
    tenant_transaction_scope,
)
from pitchlog.sync import port_guard
from pitchlog.sync.change_path import apply_p3_change
from pitchlog.sync.crash_points import reach
from pitchlog.sync.gate import (
    RG1Blocked,
    game_accessible,
    gated_e1_writer,
    gated_writer,
)
from pitchlog.sync.idempotency import (
    D5Candidate,
    classify_request_d5,
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
from pitchlog.sync.tokens import (
    RECORDING_GENERATION_READ_COLUMNS,
    RecordingGenerationByNumberReadToken,
    RecordingGenerationReadToken,
)

type ApplyResult = AckResult | ChangeResult | Literal["B6", "B7"]
type D1Result = P1Result | RejectionResult

_GENERATION_COLUMNS = RECORDING_GENERATION_READ_COLUMNS


@dataclass(frozen=True, slots=True)
class _BatchPreflight:
    """④の内部候補と、⑤より前に読んだ D3 を外部確定まで保持する。"""

    d3: int
    candidates: tuple[D5Candidate, ...]
    has_recording_right: bool
    current_generation: int
    # 要求の D4 が指す世代の D3。現世代の要求では d3 と同じ(省略時も同じ)。
    request_d3: int | None = None


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
                from pitchlog.sync.prefix_path import _LEGACY_LOCKED_SOURCE
                from pitchlog.sync.source_binding import (
                    _legacy_entry_scope,
                    legacy_dto_source,
                )

                with _legacy_entry_scope(context, request, registrations) as entry:
                    bindings = tuple(
                        legacy_dto_source(
                            entry, request, event, registrations.get(event.d5)
                        )
                        for event in request.events
                    )
                    return _preflight_in_scope(
                        scope,
                        context,
                        request,
                        rights,
                        gated.writer,
                        bindings,
                        source=_LEGACY_LOCKED_SOURCE,
                    )


def _preflight_in_scope(
    scope, context, request, rights, writer, source_bindings, *, source
):
    """既④/D3/⑤本体。実scopeと必須sourceを受け、自前TXを開かない。"""
    from pitchlog.repositories.transaction import _port_predecision_phase
    from pitchlog.sync.prefix_path import _LEGACY_LOCKED_SOURCE
    from pitchlog.sync.source_binding import (
        SourceBindingError,
        _E1CoreSource,
        read_selected_event_source,
    )

    if source is not _LEGACY_LOCKED_SOURCE and type(source) is not _E1CoreSource:
        raise SourceBindingError("preflight sourceが不正")

    fingerprints = tuple(
        read_selected_event_source(
            binding, context=context, request=request, event=event
        ).event_fingerprint
        for binding, event in zip(source_bindings, request.events, strict=True)
    )
    candidates = classify_request_d5(scope, request, fingerprints)
    rows = scope.run(RecordingGenerationReadToken(UUID(request.game_id))).rows
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
            RecordingGenerationByNumberReadToken(UUID(request.game_id), int(request.d4))
        ).rows
        if len(request_rows) == 1:
            value = _cell(request_rows[0], _GENERATION_COLUMNS, "confirmed_watermark")
            if type(value) is not int:
                raise RuntimeError("D3 の型が不正")
            request_d3 = value
    has_right = True
    if any(candidate.kind == "unused" for candidate in candidates):
        port_guard.require_registered_port(rights)
        with (
            nullcontext()
            if source is _LEGACY_LOCKED_SOURCE
            else _port_predecision_phase(scope, "rights")
        ):
            has_right = rights.holds_recording_right(
                request.game_id, request.d4, request.v12, writer
            )
    return _BatchPreflight(d3, candidates, has_right, generation, request_d3)


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
    from pitchlog.sync.prefix_path import _LEGACY_LOCKED_SOURCE

    reach("before_transaction")
    selected_path = _select_d1_path(request, source=_LEGACY_LOCKED_SOURCE)
    try:
        if selected_path == "P4":
            outcome: D1Result = apply_rejection_or_escrow(
                context, event, rights, request.v12, path="P4", reason=None
            )
        elif selected_path == "P2":
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
        from pitchlog.sync.prefix_path import _LEGACY_LOCKED_SOURCE

        arguments = _rejection_arguments(error, source=_LEGACY_LOCKED_SOURCE)
        if arguments is None:
            raise
        outcome = apply_rejection_or_escrow(
            context,
            event,
            rights,
            request.v12,
            path=cast(RejectionPath, request.path),
            registration=registration,
            **arguments,
        )
    reach("after_transaction")
    return outcome


def _select_d1_path(request, *, source):
    """旧局所/再掲とE1の経路選択を単一化する。"""
    from pitchlog.sync.prefix_path import _LEGACY_LOCKED_SOURCE
    from pitchlog.sync.source_binding import SourceBindingError, _E1CoreSource

    if source is not _LEGACY_LOCKED_SOURCE and type(source) is not _E1CoreSource:
        raise SourceBindingError("E1経路sourceが不正")
    return request.path if request.path in ("P2", "P4") else "P1"


def _rejection_arguments(error, *, source):
    """T8/T9の写像を両入口で共有する。書込開始後はcallerがこの口へ渡さない。"""
    from pitchlog.sync.prefix_path import _LEGACY_LOCKED_SOURCE
    from pitchlog.sync.source_binding import SourceBindingError, _E1CoreSource

    if source is not _LEGACY_LOCKED_SOURCE and type(source) is not _E1CoreSource:
        raise SourceBindingError("E1拒否分岐sourceが不正")
    if error.category == "recording_rights":
        return {"reason": None, "cause": "content_rejection"}
    if error.category == "w2_violation" or isinstance(error, P1ContentRejection):
        return {
            "reason": content_reason_for_precondition(error),
            "cause": "w2_violation"
            if error.category == "w2_violation"
            else "content_rejection",
        }
    return None


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


def _replay_existing(
    context: TenantContext,
    request: SyncRequest,
    event: SyncEvent,
    rights: RecordingRightsPort,
    projection: ProjectionPort,
    validator: ContentValidationPort,
    registration: PlayerRegistration | None,
    target: P1Target | None,
) -> D1Result:
    """⑤ 不成立の要求で、既存 D5 の保存済み結果(または B3b)を再掲する。

    P1・P2 の局所経路は ④ の D5 分類で再掲・B3b を決め、⑤ には進まない。
    P4 の要求は、退避を書いた P4 の経路(P4 の指紋)で照合して再掲する。
    """
    from pitchlog.sync.prefix_path import _LEGACY_LOCKED_SOURCE

    reach("before_transaction")
    selected_path = _select_d1_path(request, source=_LEGACY_LOCKED_SOURCE)
    if selected_path == "P4":
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
    elif selected_path == "P2":
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


def _is_replay(result: D1Result) -> bool:
    """保存済み結果の再掲かを返す。"""
    return result.replayed


def _replay_e1_without_binding(
    context: TenantContext,
    request: SyncRequest,
    fingerprints: tuple[str, ...],
) -> AckResult | Literal["B6", "B7"] | None:
    """③認可後・V12前の D5 先行分類を writer binding 前に一度だけ行う。

    正本 sync-protocol DI1〜DI3 と 7-3 の再掲を、単球F1入口（1要求1イベント）
    の範囲で実装する。同一内容の保存済み D5 は再適用せず、受理→A5「重複」・
    拒否→同理由・退避→同退避として返し、異内容は B3b とする。未使用 D5 を
    含む要求は通常の段階順（⑤以降）へ戻すため ``None`` を返す。

    Args:
        context: 実認証済みのテナント文脈。
        request: S-1 外形を通過した同期要求。
        fingerprints: 原wireから凍結した各イベントの指紋（要求順）。

    Returns:
        再掲 ACK、ACK を返さない境界 ``"B6"``/``"B7"``、または通常経路へ戻す
        ``None``。

    Raises:
        SourceBindingError: 入力が単球F1入口の閉形式に合わない場合。
    """
    from pitchlog.repositories.rg1 import RG1Unavailable, read_rg1_open
    from pitchlog.sync.idempotency import classify_d5
    from pitchlog.sync.prefix_path import _candidate_result
    from pitchlog.sync.source_binding import SourceBindingError

    if (
        type(context) is not TenantContext
        or not context._has_valid_integrity_proof()
        or type(request) is not SyncRequest
        or type(fingerprints) is not tuple
        or len(fingerprints) != len(request.events)
        or any(type(value) is not str for value in fingerprints)
    ):
        raise SourceBindingError("E1再掲の入力が不正")
    if request.path != "P2" or len(request.events) != 1:
        # 単球F1入口の範囲外は流儀どおり後段（_E1OutOfScope）へ委ねる。
        return None
    event = request.events[0]
    if type(event.d1) is not int or event.d1 != 1 or type(event.d4) is not str:
        return None
    game_id = UUID(request.game_id)
    if not game_accessible(context, game_id, tenant_transaction_scope):
        return "B6"
    with tenant_transaction_scope(context) as scope:
        try:
            read_rg1_open(scope)
        except RG1Unavailable:
            return "B7"
        rows = scope.run(RecordingGenerationReadToken(game_id)).rows
        if len(rows) != 1:
            raise RuntimeError("自テナントの記録権世代行が一件ではない")
        d3 = _cell(rows[0], _GENERATION_COLUMNS, "confirmed_watermark")
        if type(d3) is not int:
            raise RuntimeError("D3 の型が不正")
        candidate = classify_d5(scope, UUID(event.d5), fingerprints[0], "P2")
    if candidate.kind == "unused":
        # 未使用 D5 は ⑤ 以降（V12・content・order）が正本の段階順。
        return None
    result = _candidate_result(candidate, d3)
    if result is None:
        return None
    state = _event_state(result)
    reason = result.reason or (
        "同じ D5 の内容が異なる" if result.boundary == "B3b" else None
    )
    advanced = max(d3, result.d3) if result.accepted else d3
    boundary: Literal["B1", "B2", "B3", "B4"] = "B1"
    b3_branch: Literal["B3a", "B3b", "O4"] | None = None
    if not (state == "退避"):
        # 再掲の退避は境界結果を決めない（SP 変更履歴 U-14）。
        if result.boundary in ("B3", "B3a", "B3b"):
            boundary = "B3"
            b3_branch = "O4" if result.boundary == "B3" else result.boundary
        elif result.boundary == "B4":
            boundary = "B4"
    return AckResult(
        boundary,
        advanced,
        (A5Result(event.d4, event.d1, event.d5, state, reason),),
        b3_branch,
        reason if boundary == "B3" else None,
        dict(result.temporary_id_mapping) if isinstance(result, P1Result) else None,
    )


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
    from pitchlog.sync.prefix_path import _LEGACY_LOCKED_SOURCE

    return _drive_d1_ack(
        context,
        request,
        rights,
        projection,
        validator,
        preflight,
        registrations,
        targets,
        source=_LEGACY_LOCKED_SOURCE,
        event_runner=_run_d1_event,
        escrow_runner=_escrow_without_right,
        replay_runner=_replay_existing,
    )


def _drive_d1_ack(
    context,
    request,
    rights,
    projection,
    validator,
    preflight,
    registrations,
    targets,
    *,
    source,
    event_runner,
    escrow_runner,
    replay_runner,
):
    """一つの逐次foldを両入口で使う。実行関数は私有kernelが束縛する。"""
    from pitchlog.sync.prefix_path import _LEGACY_LOCKED_SOURCE
    from pitchlog.sync.source_binding import SourceBindingError, _E1CoreSource

    if source is not _LEGACY_LOCKED_SOURCE and type(source) is not _E1CoreSource:
        raise SourceBindingError("E1 ACK sourceが不正")
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
    d3 = preflight.d3 if preflight.request_d3 is None else preflight.request_d3
    boundary: Literal["B1", "B2", "B3", "B4"] = "B1"
    b3_branch: Literal["B3a", "B3b", "O4"] | None = None
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
        registration = registrations[event.d5] if event.d5 in registrations else None
        target = targets[event.d5] if event.d5 in targets else None
        if not preflight.has_recording_right:
            if candidates[event.d5].kind == "conflict":
                # ⑤ の B4 では ⑥ に進まない。異内容候補は拒否原本を作らず未処理。
                a5.append(A5Result(event.d4, event.d1, event.d5, "未処理"))
                continue
            if candidates[event.d5].kind == "unused":
                result: D1Result = escrow_runner(
                    context,
                    request,
                    event,
                    rights,
                    registration,
                )
            else:
                result = replay_runner(
                    context,
                    request,
                    event,
                    rights,
                    projection,
                    validator,
                    registration,
                    target,
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
            result = event_runner(
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
        next_d1 = max(next_d1, event.d1 + 1)
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
            b3_branch = "O4" if result.boundary == "B3" else result.boundary
            reason = event_reason
            stopped = True
        elif result.boundary == "B4":
            boundary = "B4"
            stopped = True

    return AckResult(boundary, d3, tuple(a5), b3_branch, reason, mappings)


class _E1OutOfScope(RuntimeError):
    """真正issuerが供給されても単球F1以外は未対応の固定拒否。"""


def _read_reference_device_state(context, reference_device):
    """②の未登録専用readだけを実scopeへ送り、型不正をfalseにしない。"""
    from pitchlog.repositories.first_ball import _ReadFirstBallDeviceStateToken

    with tenant_transaction_scope(context) as scope:
        result = scope.run_function(_ReadFirstBallDeviceStateToken(reference_device))
        if (
            type(result.rows) is not tuple
            or len(result.rows) != 1
            or type(result.rows[0]) is not tuple
            or len(result.rows[0]) != 1
            or type(result.rows[0][0]) is not bool
        ):
            raise RuntimeError("端末状態の読取結果が不正")
        return result.rows[0][0]


def _apply_e1_f1(
    receipt,
    context,
    request,
    *,
    entry_token,
    phase,
    cookie,
    reference_device,
    control,
    rights,
    projection,
    validator,
    registrations=None,
    targets=None,
):
    """未公開のF1私有入口。実issuer/Port/登録不足は閉拒否する。"""
    from pitchlog.repositories.rg1 import RG1Unavailable, read_rg1_open
    from pitchlog.sync.control_provider.binding_control import BindingControl
    from pitchlog.sync.control_provider.evidence import EventPhaseBinding
    from pitchlog.sync.control_provider.writer_binding import _verify_bound_device
    from pitchlog.sync.prefix_path import (
        _apply_locked_in_scope,
        _D5Race,
        _NoWriteStop,
    )
    from pitchlog.sync.rejection import _apply_rejection_in_scope, _RaceReplay
    from pitchlog.sync.source_binding import (
        SourceBindingError,
        _E1CoreSource,
        _receipt_for_entry,
        e1_event_source,
    )

    state = _receipt_for_entry(receipt, entry_token)
    if (
        state.context is not context
        or state.request is not request
        or type(context) is not TenantContext
        or not context._has_valid_integrity_proof()
        or type(phase) is not EventPhaseBinding
        or type(cookie) is not str
        or not cookie
        or type(reference_device) is not UUID
        or type(control) is not BindingControl
    ):
        raise SourceBindingError("E1の入力又は文脈が不正")
    if not _read_reference_device_state(context, reference_device):
        return "B5"
    if not game_accessible(context, UUID(request.game_id), tenant_transaction_scope):
        return "B6"
    if len(request.events) != 1 or request.events[0].d1 != 1:
        raise _E1OutOfScope("E1要求はF1の範囲外")
    event = request.events[0]
    registrations = registrations or {}
    targets = targets or {}
    binding = e1_event_source(receipt, 1)
    rollback_marker = SourceBindingError("E1のbound文脈を拒否")
    rejected_boundary = None
    source = None
    preflight = None

    try:
        with tenant_transaction_scope(context) as scope:
            with _sync_apply_active():
                # この呼出点だけB7へ写し、bind_writer内部の例外は伝播。
                try:
                    read_rg1_open(scope)
                except RG1Unavailable:
                    return "B7"
                bound = control.bind_writer(scope, context, phase, cookie=cookie)
                with gated_e1_writer(scope, rights) as gated:
                    device = _verify_bound_device(
                        bound,
                        reference_device,
                        request.game_id,
                        presentation=state.device_presentation,
                    )
                    if device != "match":
                        rejected_boundary = "B6" if device == "different_game" else "B5"
                        raise rollback_marker
                    source = _E1CoreSource(
                        binding,
                        scope=scope,
                        context=context,
                        request=request,
                        event=event,
                        phase=phase,
                        bound=bound,
                    )
                    preflight = _preflight_in_scope(
                        scope,
                        context,
                        request,
                        rights,
                        gated.writer,
                        (binding,),
                        source=source,
                    )

                    def reject_one(ctx, req, current, port, registration):
                        source.read(scope, current)
                        return _apply_rejection_in_scope(
                            scope,
                            current,
                            port,
                            req.v12,
                            req.path,
                            registration,
                            None,
                            "content_rejection",
                            gated.writer,
                            source=source,
                        )

                    def run_one(
                        ctx,
                        req,
                        current,
                        port,
                        projection_port,
                        validation_port,
                        registration,
                        target,
                    ):
                        source.read(scope, current)
                        path = _select_d1_path(req, source=source)
                        try:
                            if path == "P4":
                                return reject_one(ctx, req, current, port, registration)
                            from pitchlog.sync.ordering import _assign_d2

                            return _apply_locked_in_scope(
                                scope,
                                current,
                                port,
                                projection_port,
                                validation_port,
                                req.v12,
                                registration,
                                target,
                                source=source,
                                path=path,
                                order_resolver=_assign_d2 if path == "P2" else None,
                                writer=gated.writer,
                            )
                        except P1PreconditionError as error:
                            if source.write_started:
                                raise
                            arguments = _rejection_arguments(error, source=source)
                            if arguments is None:
                                raise
                            return _apply_rejection_in_scope(
                                scope,
                                current,
                                port,
                                req.v12,
                                req.path,
                                registration,
                                arguments["reason"],
                                arguments["cause"],
                                gated.writer,
                                source=source,
                            )

                    def replay_one(
                        ctx,
                        req,
                        current,
                        port,
                        projection_port,
                        validation_port,
                        registration,
                        target,
                    ):
                        return run_one(
                            ctx,
                            req,
                            current,
                            port,
                            projection_port,
                            validation_port,
                            registration,
                            target,
                        )

                    result = _drive_d1_ack(
                        context,
                        request,
                        rights,
                        projection,
                        validator,
                        preflight,
                        registrations,
                        targets,
                        source=source,
                        event_runner=run_one,
                        escrow_runner=reject_one,
                        replay_runner=replay_one,
                    )
                    # 新規受理/T8/T9だけ⑧を1回発火。DI2再掲は0回。
                    if (
                        isinstance(result, AckResult)
                        and any(
                            item.state in ("受理", "拒否", "退避") for item in result.a5
                        )
                        and source.write_started
                    ):
                        gated.mark_written()
                    return result
    except SourceBindingError as error:
        if error is rollback_marker and rejected_boundary is not None:
            return rejected_boundary
        raise
    except RG1Blocked:
        return "B7"
    except (_D5Race, _NoWriteStop, _RaceReplay) as stopped:
        # 既scope hookがrollback/lease終結を確認した後、保存済み純結果だけfold。
        if source is None or preflight is None:
            raise
        saved = stopped.result

        def replay_saved(*args):
            return saved

        return _drive_d1_ack(
            context,
            request,
            rights,
            projection,
            validator,
            preflight,
            registrations,
            targets,
            source=source,
            event_runner=replay_saved,
            escrow_runner=replay_saved,
            replay_runner=replay_saved,
        )
