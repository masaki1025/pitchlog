"""同期HTTPのP1/P2と、独立したP3変更入口。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from pitchlog.api.request_presentation import require_presented_token
from pitchlog.api.schemas.recording_ack import RecordingAckResponse
from pitchlog.api.tenant_access import TenantMatchedRoute, require_tenant_access
from pitchlog.db.sync_protocol.models import EventSlot
from pitchlog.durable_rights_ledger.adapter import LedgerUnavailable
from pitchlog.recording_rights.initial_grant_broker import InitialBrokerUnavailable
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.database_errors import DATABASE_ERRORS
from pitchlog.repositories.initial_recording_right import (
    InitialGrantUnavailable,
    _credential_digest,
)
from pitchlog.repositories.nonplay_prefix import NonplaySourceUnavailable
from pitchlog.repositories.ordinary_pitch_operations import OrdinaryPlayRowError
from pitchlog.repositories.ordinary_prefix import OrdinaryPrefixError
from pitchlog.repositories.ordinary_prefix_read import (
    OrdinaryPrefixView,
    _function_one,
    read_lineup_prefix,
)
from pitchlog.repositories.past_correction_current import (
    PastCorrectionCurrentUnavailable,
    verify_p3_current_packet,
)
from pitchlog.repositories.past_correction_right import _ReadP3CurrentToken
from pitchlog.repositories.past_correction_source import (
    PastCorrectionSourceUnavailable,
    read_past_correction_v3_source_snapshot,
)
from pitchlog.repositories.transaction import tenant_transaction_scope
from pitchlog.sync.apply import (
    _apply_e1_f1,
    _apply_e1_p3,
    _E1OutOfScope,
    _replay_e1_without_binding,
    _replay_p3_without_binding,
)
from pitchlog.sync.attempt_recovery import recover_sync_attempt
from pitchlog.sync.control_provider.binding_client import (
    BindingClientConfiguration,
    BindingClientConfigurationError,
    load_binding_client_configuration,
)
from pitchlog.sync.control_provider.binding_control import BindingControl
from pitchlog.sync.control_provider.evidence import (
    AttemptBinding,
    AuthorityBinding,
    D1lessPhaseBinding,
    EventPhaseBinding,
    sync_event_phase_id,
)
from pitchlog.sync.control_provider.writer_binding import (
    WriterBindingUnavailable,
    _issue_device_presentation,
)
from pitchlog.sync.first_ball_ports import FirstBallContentValidationPort
from pitchlog.sync.first_ball_projection import FirstBallProjectionPort
from pitchlog.sync.first_ball_recording_rights import FirstBallRecordingRightsPort
from pitchlog.sync.http_recording_key import _decode_recording_key
from pitchlog.sync.idempotency import _json_value
from pitchlog.sync.lifecycle_execution import LifecycleExecutionError
from pitchlog.sync.model import (
    AcceptedChangeResult,
    AckResult,
    RejectedChangeResult,
    RequestShapeError,
    SyncRequest,
)
from pitchlog.sync.ordinary_pitch_execution import OrdinaryPitchExecutionError
from pitchlog.sync.ordinary_pitch_ports import (
    LineupPrefixContentValidationPort,
    LineupPrefixProjectionPort,
    OrdinaryPitchContentValidationPort,
    OrdinaryPitchProjectionPort,
    PlayPrefixContentValidationPort,
    PlayPrefixProjectionPort,
)
from pitchlog.sync.past_correction_execution import PastCorrectionExecutionError
from pitchlog.sync.past_correction_ports import (
    PastCorrectionContentValidationPort,
    PastCorrectionProjectionPort,
)
from pitchlog.sync.past_correction_preparation import (
    PastCorrectionPreparationUnavailable,
)
from pitchlog.sync.past_correction_projection import PastCorrectionProjectionError
from pitchlog.sync.past_correction_rights import PastCorrectionRecordingRightsPort
from pitchlog.sync.source_binding import (
    SourceBindingError,
    _e1_receipt_scope,
    e1_event_source,
    selected_event_fingerprint,
)
from pitchlog.sync.substitution_execution import SubstitutionExecutionError
from pitchlog.sync.substitution_ports import (
    SubstitutionContentValidationPort,
    SubstitutionProjectionPort,
)
from pitchlog.sync.substitution_projection import SubstitutionProjectionError
from pitchlog.sync.substitution_roster import SubstitutionRosterUnavailable
from pitchlog.sync.tokens import EventSlotReadToken
from pitchlog.sync.undo_execution import UndoExecutionError
from pitchlog.sync.undo_ports import UndoContentValidationPort, UndoProjectionPort
from pitchlog.sync.wire_source import WireSourceError, freeze_wire_source

router = APIRouter(tags=["同期"], route_class=TenantMatchedRoute)


def _configuration(request: Request) -> BindingClientConfiguration:
    """起動時設定だけを使い、未設定は書込入口を閉じる。"""
    path = getattr(request.app.state, "binding_client_config_path", None)
    if path is None:
        raise HTTPException(status_code=503)
    try:
        return load_binding_client_configuration(path)
    except BindingClientConfigurationError:
        raise HTTPException(status_code=503) from None


def _phase_id(attempt: UUID, request_fingerprint: str) -> UUID:
    """同一要求の再送で同一 phase を作り、新 attempt だけを別 phase にする。"""
    return sync_event_phase_id(attempt, request_fingerprint)


def _request_path(payload: object) -> Literal["P1", "P2"]:
    """既P2と単一取消P1だけを選ぶ。V7の意味検査はD5照合後に行う。"""
    if not isinstance(payload, dict):
        raise RequestShapeError("S-1: 本文が object ではない")
    if "change" in payload:
        raise _E1OutOfScope("P3 は本入口の対象外")
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise RequestShapeError("S-1: イベント列が必要")
    if any(
        isinstance(event, dict) and event.get("event_kind") == "undo"
        for event in events
    ):
        if len(events) == 1:
            return "P1"
        raise _E1OutOfScope("取消は単一イベントP1だけを提供する")
    if any(isinstance(event, dict) and "d2" in event for event in events):
        return "P2"
    raise _E1OutOfScope("本入口は初球P2に限定する")


def _ack_body(result: AckResult) -> dict[str, object]:
    """実 AckResult だけを D1 ACK envelope へ投影する。"""
    body: dict[str, object] = {
        "advancedD3": result.d3,
        "eventResults": [
            {
                "d4": item.d4,
                "d1": item.d1,
                "d5": item.d5,
                "a5Result": item.state,
            }
            for item in result.a5
        ],
    }
    if result.temporary_id_mapping:
        body["playerIdMappings"] = [
            {"temporaryId": temporary, "officialId": official}
            for temporary, official in result.temporary_id_mapping.items()
        ]
    return RecordingAckResponse.model_validate(body).model_dump(
        by_alias=True, exclude_unset=True
    )


def _p3_body(result: AcceptedChangeResult | RejectedChangeResult) -> dict[str, object]:
    """保存済みI6と拒否を別形にし、例外や資格を応答へ写さない。"""
    if type(result) is AcceptedChangeResult:
        return {
            "boundary": result.boundary,
            "target_reference": _json_value(result.target_reference),
            "expected_version": result.expected_version,
            "d5": result.d5,
            "confirmed_content": _json_value(result.confirmed_content),
            "accepted_at": result.accepted_at,
        }
    if type(result) is RejectedChangeResult:
        return {"boundary": result.boundary, "d5": result.d5, "reason": result.reason}
    raise TypeError("P3結果型が不一致")


@router.get(
    "/games/{game_id}/sync/change-target/{d1}",
    operation_id="read_sync_change_target",
)
def read_sync_change_target(
    game_id: UUID,
    d1: int,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> JSONResponse:
    """同tenantの真正v3原本と対象slotを同TXで照合し、有限P3版だけを返す。"""
    try:
        with tenant_transaction_scope(context) as scope:
            snapshot = read_past_correction_v3_source_snapshot(scope, game_id, d1)
            checkpoint = snapshot.checkpoint
            if checkpoint is None:
                raise PastCorrectionSourceUnavailable("P3対象のCPがありません")
            saved = snapshot.rows[d1 - 1]
            rows = scope.run(
                EventSlotReadToken(game_id, snapshot.internal_generation, d1)
            ).rows
            columns = tuple(EventSlot.__table__.c.keys())
            if len(rows) != 1 or len(rows[0]) != len(columns):
                raise PastCorrectionSourceUnavailable("P3対象版がありません")
            slot = dict(zip(columns, rows[0], strict=True))
            if (
                slot["tenant_id"] != context.tenant_id
                or slot["game_id"] != game_id
                or slot["generation"] != snapshot.internal_generation
                or slot["d1"] != d1
                or type(slot["confirmed_version"]) is not int
                or slot["confirmed_version"] != 1
                or saved.play_row is None
                or saved.play_row.get("source_event_id")
                != str(saved.source_event_id)
                or saved.play_row.get("id")
                != saved.calculation.request.play_identity.play_id
                or checkpoint.wire_d4
                != saved.calculation.response.value.next_prefix_ref.generation
            ):
                raise PastCorrectionSourceUnavailable("P3対象版と原本が不一致")
            current_ref = snapshot.rows[-1].calculation.response.value.next_prefix_ref
            return JSONResponse(
                {
                    "target_reference": {
                        "game": str(game_id),
                        "d4": checkpoint.wire_d4,
                        "d1": d1,
                    },
                    "expected_version": slot["confirmed_version"],
                    "expected_prefix_ref": current_ref.model_dump(
                        mode="json", by_alias=True, exclude_unset=True
                    ),
                    "target_event_id": str(saved.source_event_id),
                    "target_play_id": saved.play_row["id"],
                    "original_result_id": saved.calculation.request.t1.result_id,
                }
            )
    except (PastCorrectionSourceUnavailable, OrdinaryPrefixError):
        raise HTTPException(status_code=409) from None
    except DATABASE_ERRORS:
        raise HTTPException(status_code=503) from None


@router.get(
    "/games/{game_id}/sync/change-confirmation/{d1}",
    operation_id="read_sync_change_confirmation",
)
def read_sync_change_confirmation(
    game_id: UUID,
    d1: int,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> JSONResponse:
    """同read TXの現v3、P3受理原本と実slot版を結合する。"""
    if d1 < 1 or d1 > 25:
        raise HTTPException(status_code=409)
    try:
        with tenant_transaction_scope(context) as scope:
            current = read_lineup_prefix(scope, game_id, limit=25)
            if type(current) is not OrdinaryPrefixView:
                raise PastCorrectionCurrentUnavailable("現v3がありません")
            generation = _decode_recording_key(
                current.metadata.current_d4, context.tenant_id, game_id
            )
            packet = _function_one(scope, _ReadP3CurrentToken(game_id, generation))
            verified = verify_p3_current_packet(
                packet, tenant=context.tenant_id, game=game_id, generation=generation
            )
            page = current.projection.get("page")
            if (
                verified.target_d1 != d1
                or verified.checkpoint.prefix_ref
                != current.projection.get("prefix_ref")
                or verified.checkpoint.after != current.projection.get("after")
                or type(page) is not dict
                or page.get("next_cursor") is not None
            ):
                raise PastCorrectionCurrentUnavailable("P3現readとの照合が不一致")
            rows = scope.run(EventSlotReadToken(game_id, generation, d1)).rows
            columns = tuple(EventSlot.__table__.c.keys())
            if len(rows) != 1 or len(rows[0]) != len(columns):
                raise PastCorrectionCurrentUnavailable("P3対象slotがありません")
            slot = dict(zip(columns, rows[0], strict=True))
            target = verified.items[d1 - 1]["play_row"]
            if (
                slot["tenant_id"] != context.tenant_id
                or slot["game_id"] != game_id
                or slot["generation"] != generation
                or slot["d1"] != d1
                or type(slot["confirmed_version"]) is not int
                or slot["confirmed_version"] != 2
                or type(target) is not dict
                or target.get("source_event_id") != str(verified.change_event_id)
                or target.get("id")
                != verified.items[d1 - 1]["effective_play_row_id"]
            ):
                raise PastCorrectionCurrentUnavailable("P3対象版が不一致")
            play = cast(dict[str, object], target)
            return JSONResponse(
                {
                    "target_reference": {
                        "game": str(game_id),
                        "d4": current.metadata.current_d4,
                        "d1": d1,
                    },
                    "confirmed_version": slot["confirmed_version"],
                    "d5": str(verified.d5),
                    "source_event_id": str(verified.change_event_id),
                    "target_play_id": play["id"],
                    "stats_version_id": str(verified.stats_version_id),
                    "current_prefix_ref": verified.checkpoint.prefix_ref.model_dump(
                        mode="json", by_alias=True, exclude_unset=True
                    ),
                    "current_after": verified.checkpoint.after.model_dump(
                        mode="json", by_alias=True, exclude_unset=True
                    ),
                }
            )
    except (
        PastCorrectionCurrentUnavailable,
        OrdinaryPrefixError,
        InitialBrokerUnavailable,
        ValueError,
    ):
        raise HTTPException(status_code=409) from None
    except DATABASE_ERRORS:
        raise HTTPException(status_code=503) from None


@router.post("/games/{game_id}/sync/change", operation_id="sync_change")
def sync_change(
    game_id: UUID,
    payload: dict[str, object],
    request: Request,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
    cookie: Annotated[str, Depends(require_presented_token)],
    device_id: Annotated[UUID, Header(alias="X-Pitchlog-Device-Id")],
    device_credential: Annotated[str, Header(alias="X-Pitchlog-Device-Credential")],
    attempt: Annotated[UUID, Header(alias="X-Pitchlog-Sync-Attempt")],
) -> JSONResponse:
    """P3原文1件を先行再掲判定後、同writer/TXの実投影へ渡す。"""
    configuration = _configuration(request)
    try:
        sync_request = SyncRequest.from_payload("P3", str(game_id), payload)
        change = payload["change"]
        if not isinstance(change, dict):
            raise RequestShapeError("S-1: P3変更原文が不正")
        target = sync_request.events[0].v10
        if not isinstance(target, Mapping):
            raise RequestShapeError("S-1: P3対象が不正")
        target_d4 = target["d4"]
        if type(target_d4) is not str:
            raise RequestShapeError("S-1: P3対象世代が不正")
        source = freeze_wire_source(
            game_id=str(game_id),
            d4=str(target_d4),
            raw_events=(dict(change),),
            d1less=True,
        )
    except (RequestShapeError, WireSourceError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=422) from None
    try:
        credential_digest = _credential_digest(device_credential)
    except InitialGrantUnavailable:
        raise HTTPException(status_code=401) from None
    try:
        replay = _replay_p3_without_binding(
            context, sync_request, device_id, credential_digest
        )
    except DATABASE_ERRORS:
        raise HTTPException(status_code=503) from None
    if replay == "B11":
        raise HTTPException(status_code=401)
    if replay == "B12":
        raise HTTPException(status_code=404)
    if replay == "B10":
        raise HTTPException(status_code=503)
    if replay is not None:
        return JSONResponse(_p3_body(replay))
    entry_token = object()
    try:
        with _e1_receipt_scope(
            context=context,
            request=sync_request,
            source=source,
            entry_token=entry_token,
        ) as receipt:
            binding = e1_event_source(receipt, 1)
            _issue_device_presentation(
                receipt,
                entry_token,
                reference_device=device_id,
                credential_digest=credential_digest,
            )
            event = sync_request.events[0]
            try:
                target_generation = _decode_recording_key(
                    target_d4, context.tenant_id, game_id
                )
            except InitialBrokerUnavailable:
                raise HTTPException(status_code=422) from None
            attempt_binding = AttemptBinding(
                AuthorityBinding(
                    configuration.control_instance,
                    configuration.business_instance,
                    configuration.restore_epoch,
                ),
                context.tenant_id,
                device_id,
                game_id,
                str(target_d4),
                target_generation,
                attempt,
                1,
                source.request_fingerprint,
                1,
            )
            phase = D1lessPhaseBinding(
                attempt_binding,
                _phase_id(attempt, source.request_fingerprint),
                1,
                UUID(event.d5),
                selected_event_fingerprint(binding, event),
            )
            result = _apply_e1_p3(
                receipt,
                context,
                sync_request,
                entry_token=entry_token,
                phase=phase,
                cookie=cookie,
                reference_device=device_id,
                control=BindingControl(configuration.broker_endpoint),
                rights=PastCorrectionRecordingRightsPort(),
                projection=PastCorrectionProjectionPort(),
                validator=PastCorrectionContentValidationPort(),
            )
    except (SourceBindingError, ValueError, TypeError):
        raise HTTPException(status_code=422) from None
    except (
        LedgerUnavailable,
        WriterBindingUnavailable,
        PastCorrectionExecutionError,
        PastCorrectionPreparationUnavailable,
        PastCorrectionProjectionError,
        *DATABASE_ERRORS,
    ):
        raise HTTPException(status_code=503) from None
    if result == "B11":
        raise HTTPException(status_code=401)
    if result == "B12":
        raise HTTPException(status_code=404)
    if result == "B10":
        raise HTTPException(status_code=503)
    return JSONResponse(_p3_body(result))


@router.post(
    "/games/{game_id}/sync/attempts/recover",
    operation_id="recover_sync_attempt",
)
def recover_attempt(
    game_id: UUID,
    payload: dict[str, object],
    request: Request,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
    cookie: Annotated[str, Depends(require_presented_token)],
    device_id: Annotated[UUID, Header(alias="X-Pitchlog-Device-Id")],
    device_credential: Annotated[str, Header(alias="X-Pitchlog-Device-Credential")],
    attempt: Annotated[UUID, Header(alias="X-Pitchlog-Sync-Attempt")],
) -> JSONResponse:
    """元E-1要求の旧試行を照会し、実fence/PG終結後の再送資格だけを返す。"""
    configuration = _configuration(request)
    try:
        path = _request_path(payload)
        original = SyncRequest.from_payload(path, str(game_id), payload)
        raw_events = payload["events"]
        if not isinstance(raw_events, list):
            raise RequestShapeError("S-1: イベント列が必要")
        source = freeze_wire_source(
            game_id=original.game_id,
            d4=str(original.d4),
            raw_events=tuple(
                dict(event) for event in cast(list[Mapping[str, object]], raw_events)
            ),
        )
        credential_digest = _credential_digest(device_credential)
    except InitialGrantUnavailable:
        raise HTTPException(status_code=401) from None
    except (_E1OutOfScope, RequestShapeError, WireSourceError, KeyError, TypeError):
        raise HTTPException(status_code=422) from None
    try:
        result = recover_sync_attempt(
            context,
            original,
            source,
            attempt_id=attempt,
            device_id=device_id,
            credential_digest=credential_digest,
            cookie=cookie,
            control=BindingControl(configuration.broker_endpoint),
        )
    except (LedgerUnavailable, WriterBindingUnavailable, *DATABASE_ERRORS):
        raise HTTPException(status_code=503) from None
    except ValueError:
        raise HTTPException(status_code=422) from None
    if result == "B5":
        raise HTTPException(status_code=401)
    if result == "B6":
        raise HTTPException(status_code=404)
    if result == "B7":
        raise HTTPException(status_code=503)
    return JSONResponse({"resolution": result})


@router.post(
    "/games/{game_id}/sync/events",
    operation_id="sync_events",
    response_model=RecordingAckResponse,
)
def sync_events(
    game_id: UUID,
    payload: dict[str, object],
    request: Request,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
    cookie: Annotated[str, Depends(require_presented_token)],
    device_id: Annotated[UUID, Header(alias="X-Pitchlog-Device-Id")],
    device_credential: Annotated[str, Header(alias="X-Pitchlog-Device-Credential")],
    attempt: Annotated[UUID, Header(alias="X-Pitchlog-Sync-Attempt")],
) -> JSONResponse:
    """同HTTPの実認証・実writer・実権利で1球を保存し、実ACKだけを返す。"""
    configuration = _configuration(request)
    try:
        path = _request_path(payload)
        sync_request = SyncRequest.from_payload(path, str(game_id), payload)
        raw_events = payload["events"]
        if not isinstance(raw_events, list):
            raise RequestShapeError("S-1: イベント列が必要")
        source = freeze_wire_source(
            game_id=sync_request.game_id,
            d4=str(sync_request.d4),
            raw_events=tuple(
                dict(event) for event in cast(list[Mapping[str, object]], raw_events)
            ),
        )
    except (_E1OutOfScope, RequestShapeError, WireSourceError, KeyError, TypeError):
        raise HTTPException(status_code=422) from None
    # ②B5の実端末資格を確認してから、③B6/④D5の再掲分類へ進む。
    try:
        credential_digest = _credential_digest(device_credential)
    except InitialGrantUnavailable:
        raise HTTPException(status_code=401) from None
    # DI1/DI2/DI3: ③認可後・V12前に D5 を分類し、保存済み結果だけを再掲する。
    try:
        replayed = _replay_e1_without_binding(
            context,
            sync_request,
            source.event_fingerprints,
            device_id,
            credential_digest,
        )
    except DATABASE_ERRORS:
        raise HTTPException(status_code=503) from None
    if replayed == "B5":
        raise HTTPException(status_code=401)
    if replayed == "B6":
        raise HTTPException(status_code=404)
    if replayed == "B7":
        raise HTTPException(status_code=503)
    if replayed is not None:
        return JSONResponse(_ack_body(replayed))
    if sync_request.v12 is None:
        raise HTTPException(status_code=422)
    entry_token = object()
    rights = FirstBallRecordingRightsPort()
    try:
        with _e1_receipt_scope(
            context=context,
            request=sync_request,
            source=source,
            entry_token=entry_token,
        ) as receipt:
            binding = e1_event_source(receipt, 1)
            event = sync_request.events[0]
            # 同HTTP受付へ実端末提示を一度だけ結ぶ。発行後は受付の寿命で失効する。
            _issue_device_presentation(
                receipt,
                entry_token,
                reference_device=device_id,
                credential_digest=credential_digest,
            )
            internal_key = _decode_recording_key(
                str(sync_request.d4), context.tenant_id, game_id
            )
            attempt_binding = AttemptBinding(
                AuthorityBinding(
                    configuration.control_instance,
                    configuration.business_instance,
                    configuration.restore_epoch,
                ),
                context.tenant_id,
                device_id,
                game_id,
                str(sync_request.d4),
                internal_key,
                attempt,
                1,
                source.request_fingerprint,
                1,
            )
            if type(event.d1) is not int:
                raise SourceBindingError("D1付き同期イベントが必要")
            phase = EventPhaseBinding(
                attempt_binding,
                _phase_id(attempt, source.request_fingerprint),
                1,
                event.d1,
                UUID(event.d5),
                selected_event_fingerprint(binding, event),
            )
            ordinary = (
                isinstance(event.v7, Mapping)
                and event.v7.get("formatVersion") == "ordinary-pitch-play-v1"
            )
            play_prefix = (
                isinstance(event.v7, Mapping)
                and event.v7.get("formatVersion") == "play-prefix-play-v2"
            )
            lineup_prefix = (
                isinstance(event.v7, Mapping)
                and event.v7.get("formatVersion") == "play-prefix-play-v3"
            )
            undo = event.v5 == "undo"
            from pitchlog.sync.lifecycle_ports import (
                LifecycleContentValidationPort,
                LifecycleProjectionPort,
            )

            lifecycle = (
                event.v5 in {"game_end_declaration", "game_reopen"}
                and isinstance(event.v7, Mapping)
                and event.v7.get("formatVersion") == "native-game-lifecycle-v1"
            )
            substitution = (
                event.v5 == "substitution"
                and isinstance(event.v7, Mapping)
                and event.v7.get("formatVersion") == "substitution-event-v1"
            )
            if (
                not undo
                and not lifecycle
                and not substitution
                and isinstance(event.v7, Mapping)
                and event.v7.get("formatVersion")
                not in {
                    "first-ball-play-v1",
                    "ordinary-pitch-play-v1",
                    "play-prefix-play-v2",
                    "play-prefix-play-v3",
                }
            ):
                raise _E1OutOfScope("未知payload mode")
            result = _apply_e1_f1(
                receipt,
                context,
                sync_request,
                entry_token=entry_token,
                phase=phase,
                cookie=cookie,
                reference_device=device_id,
                control=BindingControl(configuration.broker_endpoint),
                rights=rights,
                projection=(
                    LifecycleProjectionPort()
                    if lifecycle
                    else UndoProjectionPort()
                    if undo
                    else SubstitutionProjectionPort()
                    if substitution
                    else LineupPrefixProjectionPort()
                    if lineup_prefix
                    else PlayPrefixProjectionPort()
                    if play_prefix
                    else OrdinaryPitchProjectionPort()
                    if ordinary
                    else FirstBallProjectionPort()
                ),
                validator=(
                    LifecycleContentValidationPort()
                    if lifecycle
                    else UndoContentValidationPort()
                    if undo
                    else SubstitutionContentValidationPort()
                    if substitution
                    else LineupPrefixContentValidationPort()
                    if lineup_prefix
                    else PlayPrefixContentValidationPort()
                    if play_prefix
                    else OrdinaryPitchContentValidationPort()
                    if ordinary
                    else FirstBallContentValidationPort()
                ),
            )
    except _E1OutOfScope:
        raise HTTPException(status_code=501) from None
    except (SourceBindingError, ValueError) as error:
        if isinstance(error, SubstitutionProjectionError):
            raise HTTPException(status_code=503) from None
        raise HTTPException(status_code=422) from None
    except (
        OrdinaryPrefixError,
        OrdinaryPitchExecutionError,
        OrdinaryPlayRowError,
        UndoExecutionError,
        LifecycleExecutionError,
        SubstitutionExecutionError,
        SubstitutionRosterUnavailable,
        NonplaySourceUnavailable,
        *DATABASE_ERRORS,
    ):
        # 同TXのprefix/frame/投影不成立にACKや新要求置換可否を付与しない。
        raise HTTPException(status_code=503) from None
    except WriterBindingUnavailable:
        # 実端末提示/実writer/実leaseの不成立は値を返さず閉じる。
        raise HTTPException(status_code=503) from None
    except LedgerUnavailable:
        # 試行/leaseの結果不明・同一attemptの異内容付替えはACKを返さず閉じる。
        raise HTTPException(status_code=503) from None
    if result == "B6":
        raise HTTPException(status_code=404)
    if result == "B7":
        raise HTTPException(status_code=503)
    return JSONResponse(_ack_body(result))
