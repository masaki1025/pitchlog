"""準備中試合の保存値をtenant限定で取得する。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import SecretStr

from pitchlog.api.request_presentation import require_presented_token
from pitchlog.api.schemas.base import Page
from pitchlog.api.schemas.game_start import (
    GameStartRequest,
    InitialDeviceEnrollmentResponse,
    InitialGameStartResponse,
)
from pitchlog.api.schemas.games import (
    PreparationOptionsRequest,
    PreparingGameCreate,
    PreparingGameListRequest,
    PreparingGamePreparationOptions,
    PreparingGameRead,
    _decode_preparing_snapshot,
    encode_preparing_game_cursor,
)
from pitchlog.api.tenant_access import (
    TenantMatchedRoute,
    _canonical_header,
    require_tenant_access,
)
from pitchlog.db.game_state.rule_snapshot import encode_applied_rules
from pitchlog.recording_rights.initial_grant_broker import (
    _BrokerCommand,
    _BrokerIdentity,
    _encode_initial_reply,
    _EnrollDeviceCommand,
    _initial_reply_source,
    _InitialBrokerClient,
    _ResolveStartCommand,
    _StartInitialGameCommand,
)
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.game_start import InitialStartPayload, _entries
from pitchlog.repositories.games import PreparingGameDetailToken, PreparingGameListToken
from pitchlog.repositories.rule_resolution import RuleResolutionError
from pitchlog.repositories.tokens import ImmutableValue
from pitchlog.repositories.transaction import tenant_transaction_scope
from pitchlog.services.game_creation import (
    PreparingGameCreationError,
    create_preparing_game,
    read_preparation_options,
)

router = APIRouter(tags=["準備中試合"], route_class=TenantMatchedRoute)
_FIELDS = (
    "id",
    "scheduled_at",
    "game_type_key",
    "tournament_key",
    "away_team_record_id",
    "home_team_record_id",
    "plate_umpire",
    "section_label",
    "week_label",
    "day_label",
    "game_number_label",
    "status",
    "applied_rules",
)


def _read_game(row: tuple[ImmutableValue, ...]) -> PreparingGameRead:
    """scope内で保存snapshotとDTOの全列を検証する。"""
    values: dict[str, object] = dict(zip(_FIELDS, row, strict=True))
    values["applied_rules"] = encode_applied_rules(_decode_preparing_snapshot(row[-1]))
    return PreparingGameRead.model_validate(values)


@router.get(
    "/games", response_model=Page[PreparingGameRead], operation_id="preparing_game_list"
)
def list_preparing_games(
    query: Annotated[PreparingGameListRequest, Query()],
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> Page[PreparingGameRead]:
    """可視な準備中試合を最大limit件と次cursorで返す。"""
    try:
        with tenant_transaction_scope(context) as scope:
            rows = scope.run(PreparingGameListToken(query.limit, query.cursor)).rows
            items = [_read_game(row) for row in rows[: query.limit]]
            page = Page[PreparingGameRead](
                items=items,
                next_cursor=(
                    encode_preparing_game_cursor(items[-1].scheduled_at, items[-1].id)
                    if len(rows) > query.limit
                    else None
                ),
            )
        return page
    except Exception:
        # rollback後に固定外形だけを返し、DB値や原例外を公開しない。
        raise HTTPException(status_code=503) from None


@router.get(
    "/games/preparation-options",
    response_model=PreparingGamePreparationOptions,
    operation_id="preparing_game_preparation_options",
)
def preparation_options(
    query: Annotated[PreparationOptionsRequest, Query()],
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> PreparingGamePreparationOptions:
    """認証/C2を先に確認し、有効大会の1ページと固定区分を返す。"""
    try:
        with tenant_transaction_scope(context) as scope:
            page = read_preparation_options(scope, query)
        return page
    except Exception:
        raise HTTPException(status_code=503) from None


@router.post(
    "/games",
    response_model=PreparingGameRead,
    status_code=201,
    operation_id="preparing_game_create",
)
def create_game(
    body: PreparingGameCreate,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> PreparingGameRead:
    """正規serviceの例外をscope外へ伝播し、commit完了後だけ201を返す。"""
    try:
        with tenant_transaction_scope(context) as scope:
            candidate = create_preparing_game(scope, body)
        return candidate
    except RuleResolutionError as error:
        status = {
            "stage_a_unsupported": 422,
            "rule_not_available": 404,
            "invalid_rule": 409,
            "outcome_unconfirmed": 503,
        }[error.code]
        raise HTTPException(status_code=status) from None
    except PreparingGameCreationError as error:
        status = {
            "not_available": 404,
            "tournament_name_conflict": 409,
            "outcome_unconfirmed": 503,
        }[error.code]
        raise HTTPException(status_code=status) from None
    except Exception:
        # 実RG1常閉・競合・commit失敗もrollback後の非成功に閉じる。
        raise HTTPException(status_code=503) from None


@router.get(
    "/games/{game_id}",
    response_model=PreparingGameRead,
    operation_id="preparing_game_detail",
)
def read_preparing_game(
    game_id: UUID,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> PreparingGameRead:
    """不可視・別tenant・不存在を同じ404へ閉じる。"""
    try:
        with tenant_transaction_scope(context) as scope:
            rows = scope.run(PreparingGameDetailToken(game_id)).rows
            item = _read_game(rows[0]) if rows else None
    except Exception:
        raise HTTPException(status_code=503) from None
    if item is None:
        raise HTTPException(status_code=404)
    return item


def _initial_identity(
    request: Request,
    context: TenantContext,
    cookie: str,
) -> _BrokerIdentity:
    """既C2が照合した公開metadataと原Cookieだけを閉commandへ渡す。"""
    return _BrokerIdentity(
        expected_tenant_id=context.tenant_id,
        challenge=UUID(_canonical_header(request, "X-Pitchlog-Tenant-Challenge")),
        cookie=SecretStr(cookie),
    )


def _initial_response(command: _BrokerCommand) -> JSONResponse:
    """一回通信の照合済み成功だけを専用wireからHTTPへ投影する。"""
    try:
        reply = _InitialBrokerClient().call(command)
        # 専用wireは同command/challenge/ownerも再照合し、秘密を通常dumpしない。
        _encode_initial_reply(command, reply)
        wire = _initial_reply_source(command, reply)
        if reply.status in ("enrolled", "started"):
            return JSONResponse(
                content=wire["value"], headers={"Cache-Control": "no-store"}
            )
        status = (
            404
            if reply.status == "denied"
            else 409
            if reply.status == "conflict"
            else 503
        )
    except Exception:
        # timeout/切断/原例外から業務取消や再試行可を推測せず、値をlogへ出さない。
        status = 503
    raise HTTPException(status_code=status) from None


def _initial_start_command(
    payload: GameStartRequest,
    game_id: UUID,
    identity: _BrokerIdentity,
) -> _StartInitialGameCommand:
    """既外形変換だけを使い、attempt/指紋/名簿業務判定はworkerへ残す。"""
    try:
        return _StartInitialGameCommand(
            identity=identity,
            game_id=game_id,
            start_request_id=payload.start_request_id,
            device_id=payload.device_id,
            device_credential=payload.device_credential,
            payload=InitialStartPayload(_entries(payload.away), _entries(payload.home)),
        )
    except Exception:
        pass
    raise HTTPException(status_code=422) from None


@router.post(
    "/devices/enroll",
    response_model=InitialDeviceEnrollmentResponse,
    operation_id="initial_device_enroll",
)
def enroll_initial_device(
    request: Request,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
    cookie: Annotated[str, Depends(require_presented_token)],
) -> JSONResponse:
    """同tenantの登録要求を実workerへ一度だけ渡す。"""
    return _initial_response(
        _EnrollDeviceCommand(_initial_identity(request, context, cookie))
    )


@router.post(
    "/games/{game_id}/start",
    response_model=InitialGameStartResponse,
    operation_id="initial_game_start",
)
def start_initial_game(
    game_id: UUID,
    payload: GameStartRequest,
    request: Request,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
    cookie: Annotated[str, Depends(require_presented_token)],
) -> JSONResponse:
    """元要求の全入力を送り、workerの実commit後応答だけを返す。"""
    return _initial_response(
        _initial_start_command(
            payload,
            game_id,
            _initial_identity(request, context, cookie),
        )
    )


@router.post(
    "/games/{game_id}/start/resolve",
    response_model=InitialGameStartResponse,
    operation_id="initial_game_start_resolve",
)
def resolve_initial_game_start(
    game_id: UUID,
    payload: GameStartRequest,
    request: Request,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
    cookie: Annotated[str, Depends(require_presented_token)],
) -> JSONResponse:
    """同元要求のcommitted再交付だけを照会し、新attemptを生成しない。"""
    return _initial_response(
        _ResolveStartCommand(
            _initial_start_command(
                payload,
                game_id,
                _initial_identity(request, context, cookie),
            )
        )
    )
