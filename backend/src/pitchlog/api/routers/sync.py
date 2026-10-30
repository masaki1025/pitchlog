"""初球P2の同期HTTP入口。

P3は本入口の対象外で、ACK P3形も発行しない（後続のMVP完成条件）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal, cast
from uuid import UUID, uuid5

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from pitchlog.api.request_presentation import require_presented_token
from pitchlog.api.tenant_access import TenantMatchedRoute, require_tenant_access
from pitchlog.durable_rights_ledger.adapter import LedgerUnavailable
from pitchlog.recording_rights.initial_grant_broker import _broker_generation
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.initial_recording_right import (
    InitialGrantUnavailable,
    _credential_digest,
)
from pitchlog.repositories.ordinary_pitch_operations import OrdinaryPlayRowError
from pitchlog.repositories.ordinary_prefix import OrdinaryPrefixError
from pitchlog.sync.apply import (
    _apply_e1_f1,
    _E1OutOfScope,
    _replay_e1_without_binding,
)
from pitchlog.sync.control_provider.binding_client import (
    BindingClientConfiguration,
    BindingClientConfigurationError,
    load_binding_client_configuration,
)
from pitchlog.sync.control_provider.binding_control import BindingControl
from pitchlog.sync.control_provider.evidence import (
    AttemptBinding,
    AuthorityBinding,
    EventPhaseBinding,
)
from pitchlog.sync.control_provider.writer_binding import (
    WriterBindingUnavailable,
    _issue_device_presentation,
)
from pitchlog.sync.first_ball_ports import FirstBallContentValidationPort
from pitchlog.sync.first_ball_projection import FirstBallProjectionPort
from pitchlog.sync.first_ball_recording_rights import FirstBallRecordingRightsPort
from pitchlog.sync.model import AckResult, RequestShapeError, SyncRequest
from pitchlog.sync.ordinary_pitch_execution import OrdinaryPitchExecutionError
from pitchlog.sync.ordinary_pitch_ports import (
    OrdinaryPitchContentValidationPort,
    OrdinaryPitchProjectionPort,
)
from pitchlog.sync.source_binding import (
    SourceBindingError,
    _e1_receipt_scope,
    e1_event_source,
    selected_event_fingerprint,
)
from pitchlog.sync.wire_source import WireSourceError, freeze_wire_source

router = APIRouter(tags=["同期"], route_class=TenantMatchedRoute)

_PHASE_NAMESPACE = UUID("00000000-0000-0000-0000-000000000000")


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
    return uuid5(_PHASE_NAMESPACE, f"{attempt}:{request_fingerprint}")


def _request_path(payload: object) -> Literal["P2"]:
    """本文の外形からP2だけを選び、他の経路は閉拒否する。"""
    if not isinstance(payload, dict):
        raise RequestShapeError("S-1: 本文が object ではない")
    if "change" in payload:
        raise _E1OutOfScope("P3 は本入口の対象外")
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise RequestShapeError("S-1: イベント列が必要")
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
    return body


@router.post("/games/{game_id}/sync/events", operation_id="sync_events")
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
    if sync_request.v12 is None:
        raise HTTPException(status_code=422)
    # DI1/DI2/DI3: ③認可後・V12前に D5 を分類し、保存済み結果だけを再掲する。
    try:
        replayed = _replay_e1_without_binding(
            context, sync_request, source.event_fingerprints
        )
    except SQLAlchemyError:
        raise HTTPException(status_code=503) from None
    if replayed == "B6":
        raise HTTPException(status_code=404)
    if replayed == "B7":
        raise HTTPException(status_code=503)
    if replayed is not None:
        return JSONResponse(_ack_body(replayed))
    try:
        credential_digest = _credential_digest(device_credential)
    except InitialGrantUnavailable:
        raise HTTPException(status_code=422) from None
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
            internal_generation = _broker_generation(
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
                internal_generation,
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
                projection=OrdinaryPitchProjectionPort()
                if ordinary
                else FirstBallProjectionPort(),
                validator=OrdinaryPitchContentValidationPort()
                if ordinary
                else FirstBallContentValidationPort(),
            )
    except _E1OutOfScope:
        raise HTTPException(status_code=501) from None
    except (SourceBindingError, ValueError):
        raise HTTPException(status_code=422) from None
    except (
        OrdinaryPrefixError,
        OrdinaryPitchExecutionError,
        OrdinaryPlayRowError,
        SQLAlchemyError,
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
