"""取消の接続spike専用HTTP入口。

製品の ``create_app`` には接続しない。実認証済みのテナント文脈・実端末提示・
実記録権・同期核の P1 経路・実DBを使い、取消イベントを 1 件だけ保存する。
再読込は保存済みイベントを正式 artifact で畳み込み、取消後の状態を返す。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Annotated, Any, cast
from uuid import UUID, uuid5

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from pitchlog.api.tenant_access import TenantMatchedRoute
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.database_errors import DATABASE_ERRORS
from pitchlog.repositories.initial_recording_right import (
    InitialGrantUnavailable,
    _credential_digest,
)
from pitchlog.repositories.ordinary_prefix import OrdinaryPrefixError
from pitchlog.repositories.started_read import (
    StartedGameView,
    StartedReadRecorded,
    StartedRecordedView,
    read_started_game,
)
from pitchlog.repositories.transaction import tenant_transaction_scope
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
from pitchlog.sync.d4_reference import encode_d4_reference
from pitchlog.sync.first_ball_recording_rights import FirstBallRecordingRightsPort
from pitchlog.sync.http_recording_key import _decode_recording_key
from pitchlog.sync.model import AckResult, RequestShapeError, SyncEvent, SyncRequest
from pitchlog.sync.prefix_path import P1Target
from pitchlog.sync.source_binding import (
    SourceBindingError,
    _e1_receipt_scope,
    e1_event_source,
    selected_event_fingerprint,
)
from pitchlog.sync.spike_undo_artifact import invoke_undo_artifact
from pitchlog.sync.spike_undo_ports import (
    EVENT_COLUMNS,
    SpikeUndoContentValidationPort,
    SpikeUndoProjectionPort,
    _cell,
    _mapping,
    _same,
    _snapshot,
)
from pitchlog.sync.tokens import (
    RECORDING_GENERATION_READ_COLUMNS,
    OperationEventReadToken,
    RecordingGenerationReadToken,
)
from pitchlog.sync.wire_source import freeze_wire_source

_TENANT_ACCESS = Callable[..., TenantContext]
_PRESENTED_TOKEN = Callable[..., object]
_PHASE_NAMESPACE = UUID("00000000-0000-0000-0000-000000000000")
_EVENT_COLUMNS = EVENT_COLUMNS
_UNDO_FORMAT = "undo-connection-spike-v1"
_READ_LIMIT = 256


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
                "reason": item.reason,
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


def _read_row(
    handle: Any, game_id: UUID, generation: int, d1: int
) -> dict[str, object] | None:
    """現行世代の D1 行を 1 件だけ読む。"""
    rows = handle.run(OperationEventReadToken(game_id, generation, d1)).rows
    if len(rows) != 1:
        return None
    row = rows[0]
    return {name: _cell(row, _EVENT_COLUMNS, name) for name in _EVENT_COLUMNS}


def _stored_result(payload: object) -> Mapping[str, object] | None:
    """保存済み取消 V7 の結果だけを読む。"""
    envelope = _mapping(payload)
    if envelope is None or envelope.get("formatVersion") != _UNDO_FORMAT:
        return None
    return _mapping(envelope.get("result"))


def _fold(
    rows: list[dict[str, object]], d4: str
) -> tuple[Mapping[str, object] | None, list[dict[str, object]]]:
    """保存済みイベントを D1 順に畳み込み、現在状態と履歴スタックを返す。"""
    current: Mapping[str, object] | None = None
    stack: list[dict[str, object]] = []
    for row in rows:
        if row.get("is_tombstone") is True:
            continue
        kind = row.get("event_kind")
        payload = row.get("payload")
        if kind == "play_input":
            snapshot = _snapshot(payload)
            if snapshot is None:
                raise OrdinaryPrefixError
            before = _mapping(snapshot.get("before"))
            after = _mapping(snapshot.get("after"))
            entry = snapshot.get("entry")
            if before is None or after is None or not isinstance(entry, Mapping):
                raise OrdinaryPrefixError
            if current is not None and not _same(before, current):
                raise OrdinaryPrefixError
            current = after
            target = {
                "game": str(row.get("game_id")),
                "d4": d4,
                "d1": row.get("d1"),
                "d5": str(row.get("d5")),
            }
            stack = [{"target": target, "entry": entry}] + stack
        elif kind == "undo":
            stored = _stored_result(payload)
            if current is None or not stack or stored is None:
                raise OrdinaryPrefixError
            result = invoke_undo_artifact(
                current, [item["entry"] for item in stack]
            )
            if result is None or not _same(stored, result):
                raise OrdinaryPrefixError
            after = _mapping(result.get("after"))
            if after is None:
                raise OrdinaryPrefixError
            current = after
            stack = stack[1:]
        else:
            # 交代・終了宣言など、このspikeが状態を畳まない種別。
            continue
    return current, stack


def _plain(value: object) -> object:
    """Immutable な JSON 値を FastAPI が直列化できる素の値へ戻す。"""
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _state_view(current: Mapping[str, object]) -> dict[str, object]:
    """状態だけを応答の閉じた形へ写す。"""
    view: dict[str, object] = {
        "stateFields": current.get("stateFields"),
        "scoreboard": current.get("scoreboard"),
    }
    cursors = current.get("battingOrderBySide")
    if cursors is not None:
        view["battingOrderBySide"] = cursors
    return view


def _build_router(
    tenant_access: _TENANT_ACCESS,
    presented_token: _PRESENTED_TOKEN,
) -> APIRouter:
    """実認証の依存を外から受けた取消spike router を作る。"""
    router = APIRouter(route_class=TenantMatchedRoute)

    @router.get("/spike/games/{game_id}/state")
    def read_state(
        game_id: UUID,
        context: TenantContext = Depends(tenant_access),
    ) -> dict[str, object]:
        """保存済みイベントから取消後の状態を再計算する。"""
        try:
            with tenant_transaction_scope(context) as scope:
                rows = scope.run(RecordingGenerationReadToken(game_id)).rows
                if len(rows) != 1:
                    raise HTTPException(status_code=404)
                generation = _cell(
                    rows[0], RECORDING_GENERATION_READ_COLUMNS, "generation"
                )
                watermark = _cell(
                    rows[0],
                    RECORDING_GENERATION_READ_COLUMNS,
                    "confirmed_watermark",
                )
                if type(generation) is not int or type(watermark) is not int:
                    raise HTTPException(status_code=409)
                d4 = encode_d4_reference(context.tenant_id, game_id, generation)
                if watermark > _READ_LIMIT:
                    return {
                        "gameId": str(game_id),
                        "generation": generation,
                        "d4": d4,
                        "watermark": watermark,
                        "nextD1": watermark + 1,
                        "truncated": True,
                        "state": None,
                        "history": [],
                        "undoTarget": None,
                        "events": [],
                    }
                events: list[dict[str, object]] = []
                for d1 in range(1, watermark + 1):
                    row = _read_row(scope, game_id, generation, d1)
                    if row is None:
                        raise HTTPException(status_code=409)
                    events.append(row)
                current, stack = _fold(events, d4)
                if current is None:
                    started = read_started_game(scope, game_id)
                    if isinstance(started, (StartedGameView, StartedRecordedView)):
                        current = started.before.model_dump(
                            mode="json", by_alias=True, exclude_unset=True
                        )
                    elif isinstance(started, StartedReadRecorded):
                        raise HTTPException(status_code=409)
                    else:
                        raise HTTPException(status_code=404)
                last = events[-1] if events else None
                target = None
                if (
                    last is not None
                    and last.get("event_kind") == "play_input"
                    and stack
                ):
                    target = stack[0]["target"]
                response = {
                    "gameId": str(game_id),
                    "generation": generation,
                    "d4": d4,
                    "watermark": watermark,
                    "nextD1": watermark + 1,
                    "truncated": False,
                    "state": _state_view(current),
                    "history": stack,
                    "undoTarget": target,
                    "events": [
                        {
                            "d1": item.get("d1"),
                            "d5": str(item.get("d5")),
                            "eventKind": item.get("event_kind"),
                            "targetD1": item.get("target_d1"),
                        }
                        for item in events
                    ],
                }
                return cast(dict[str, object], _plain(response))
        except HTTPException:
            raise
        except (OrdinaryPrefixError, SourceBindingError, ValueError, TypeError):
            raise HTTPException(status_code=409) from None
        except DATABASE_ERRORS:
            raise HTTPException(status_code=503) from None

    @router.post("/spike/games/{game_id}/undo")
    def post_undo(
        game_id: UUID,
        payload: Annotated[dict[str, Any], Body(...)],
        request: Request,
        context: TenantContext = Depends(tenant_access),
        cookie: str = Depends(presented_token),
        device_id: UUID = Header(alias="X-Pitchlog-Device-Id"),
        device_credential: str = Header(alias="X-Pitchlog-Device-Credential"),
        attempt: UUID = Header(alias="X-Pitchlog-Sync-Attempt"),
    ) -> JSONResponse:
        """実認証・実記録権・同期核 P1 で取消を 1 件保存する。"""
        configuration = _configuration(request)
        target = _mapping(payload.get("target"))
        proof = payload.get("recording_right_proof")
        d5 = payload.get("d5")
        d1 = payload.get("d1")
        event_payload = _mapping(payload.get("payload"))
        if (
            target is None
            or type(proof) is not str
            or not proof
            or type(d5) is not str
            or type(d1) is not int
            or event_payload is None
        ):
            raise HTTPException(status_code=422)
        target_game = target.get("game")
        target_d4 = target.get("d4")
        target_d1 = target.get("d1")
        if (
            target_game != str(game_id)
            or type(target_d4) is not str
            or not target_d4
            or type(target_d1) is not int
        ):
            raise HTTPException(status_code=422)
        try:
            generation = _decode_recording_key(
                target_d4, context.tenant_id, game_id
            )
            event = SyncEvent(
                d5=d5,
                game_id=str(game_id),
                d1=d1,
                d4=target_d4,
                v5="undo",
                v7=event_payload,
                v10=dict(target),
            )
            if type(event.d1) is not int:
                raise RequestShapeError("取消のD1がありません")
            sync_request = SyncRequest(
                path="P1",
                game_id=str(game_id),
                events=(event,),
                d4=target_d4,
                v12=proof,
            )
            source = freeze_wire_source(
                game_id=str(game_id),
                d4=target_d4,
                raw_events=(
                    {
                        "d5": d5,
                        "game_id": str(game_id),
                        "d1": d1,
                        "d4": target_d4,
                        "event_kind": "undo",
                        "payload": dict(event_payload),
                        "target_reference": dict(target),
                    },
                ),
            )
        except (RequestShapeError, ValueError, TypeError):
            raise HTTPException(status_code=422) from None
        # 同一D5の再送はwriter bindingより先に保存済み結果を再掲する（DI2）。
        try:
            replayed = _replay_e1_without_binding(
                context, sync_request, source.event_fingerprints, path="P1"
            )
        except DATABASE_ERRORS:
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
                _issue_device_presentation(
                    receipt,
                    entry_token,
                    reference_device=device_id,
                    credential_digest=credential_digest,
                )
                internal_key = _decode_recording_key(
                    target_d4, context.tenant_id, game_id
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
                    target_d4,
                    internal_key,
                    attempt,
                    1,
                    source.request_fingerprint,
                    1,
                )
                phase = EventPhaseBinding(
                    attempt_binding,
                    _phase_id(attempt, source.request_fingerprint),
                    1,
                    event.d1,
                    UUID(event.d5),
                    selected_event_fingerprint(binding, event),
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
                    projection=SpikeUndoProjectionPort(),
                    validator=SpikeUndoContentValidationPort(),
                    targets={
                        event.d5: P1Target(
                            game_id, generation, target_d1
                        )
                    },
                    spike_p1=True,
                )
        except _E1OutOfScope:
            raise HTTPException(status_code=501) from None
        except (SourceBindingError, ValueError):
            raise HTTPException(status_code=422) from None
        except (
            OrdinaryPrefixError,
            WriterBindingUnavailable,
            *DATABASE_ERRORS,
        ):
            raise HTTPException(status_code=503) from None
        if result == "B6":
            raise HTTPException(status_code=404)
        if result == "B7":
            raise HTTPException(status_code=503)
        if not isinstance(result, AckResult):
            raise HTTPException(status_code=501)
        return JSONResponse(_ack_body(result))

    return router


def install(
    app: Any,
    *,
    tenant_access: _TENANT_ACCESS,
    presented_token: _PRESENTED_TOKEN,
) -> None:
    """create_app() 済み app へ取消spike入口を後付けする（試験専用）。"""
    app.include_router(_build_router(tenant_access, presented_token))


__all__ = ("install",)
