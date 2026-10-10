"""選手の作成・一覧・取得・更新の入口を定義する。"""

import base64
import binascii
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query

from pitchlog.api.schemas.base import Page
from pitchlog.api.schemas.roster import (
    ROSTER_PAGE_SIZE_MAX,
    PlayerCreate,
    PlayerCreated,
    PlayerListRequest,
    PlayerRead,
    PlayerUpdate,
)
from pitchlog.api.tenant_access import require_tenant_access
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.roster import (
    PlayerCreateToken,
    PlayerReadToken,
    PlayerUpdateToken,
    RosterReferenceUnavailable,
    create_roster_player,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.repositories.transaction import tenant_transaction_scope

router = APIRouter(tags=["選手"])
_PLAYER_FIELDS = (
    "id",
    "team_record_id",
    "name",
    "throws",
    "bats",
    "uniform_number",
    "roster_status_key",
    "roster_label_key",
    "hidden_at",
)


def _run(
    context: TenantContext, operation: TenantOperationToken
) -> TenantOperationResult:
    """登録済みの単一操作を実行する。"""
    with tenant_transaction_scope(context) as scope:
        return scope.run(operation)


def _player(row: tuple[object, ...]) -> PlayerRead:
    """読み取り結果の列を応答 DTO へ写す。"""
    return PlayerRead.model_validate(dict(zip(_PLAYER_FIELDS, row, strict=True)))


def _read_player(context: TenantContext, player_id: UUID) -> PlayerRead:
    """対象テナントの選手を取得する。"""
    rows = _run(context, PlayerReadToken(limit=1, record_id=player_id)).rows
    if not rows:
        raise HTTPException(status_code=404)
    return _player(rows[0])


def _same_number_players(
    context: TenantContext, player_id: UUID, uniform_number: str | None
) -> list[PlayerRead]:
    """同一テナントの現役・未削除の同番号選手を上限付きで返す。"""
    if uniform_number is None:
        return []
    rows = _run(
        context,
        PlayerReadToken(
            limit=ROSTER_PAGE_SIZE_MAX,
            roster_status_key="active",
            uniform_number=uniform_number,
            exclude_id=player_id,
        ),
    ).rows
    return [_player(row) for row in rows[:ROSTER_PAGE_SIZE_MAX]]


def _decode_cursor(cursor: str | None) -> tuple[UUID | None, UUID | None]:
    """不透明なページ位置を複合キーへ戻す。"""
    if cursor is None:
        return None, None
    try:
        encoded = cursor + "=" * (-len(cursor) % 4)
        value = base64.b64decode(encoded, altchars=b"-_", validate=True).decode("ascii")
        team_id, player_id = value.split(":")
        if len(team_id) != 32 or len(player_id) != 32:
            raise ValueError
        return UUID(hex=team_id), UUID(hex=player_id)
    except (binascii.Error, UnicodeError, ValueError):
        raise HTTPException(status_code=422) from None


def _encode_cursor(player: PlayerRead) -> str:
    """複合キーを応答で不透明なページ位置にする。"""
    value = f"{player.team_record_id.hex}:{player.id.hex}".encode("ascii")
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


@router.post(
    "/players",
    response_model=PlayerCreated,
    status_code=201,
    operation_id="roster_player_create",
)
def create_player(
    body: PlayerCreate,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> PlayerCreated:
    """選手を登録し、登録済みの行を返す。"""
    player_id = uuid4()
    operation = PlayerCreateToken(
        id=player_id,
        team_record_id=body.team_record_id,
        name=body.name,
        roster_status_key=body.roster_status_key,
        throws=body.throws,
        bats=body.bats,
        uniform_number=body.uniform_number,
        roster_label_key=body.roster_label_key,
    )
    try:
        create_roster_player(context, operation)
    except RosterReferenceUnavailable:
        raise HTTPException(status_code=404) from None
    player = _read_player(context, player_id)
    return PlayerCreated.model_validate(
        player.model_dump()
        | {
            "same_number_players": _same_number_players(
                context, player_id, body.uniform_number
            )
        }
    )


@router.get(
    "/players",
    response_model=Page[PlayerRead],
    operation_id="roster_player_list",
)
def list_players(
    query: Annotated[PlayerListRequest, Query()],
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> Page[PlayerRead]:
    """対象テナントの選手を上限付きで一覧する。"""
    cursor_team_id, cursor_id = _decode_cursor(query.cursor)
    rows = _run(
        context,
        PlayerReadToken(
            limit=query.limit,
            team_record_id=query.team_record_id,
            roster_status_key=query.roster_status_key,
            cursor_team_record_id=cursor_team_id,
            cursor_id=cursor_id,
            include_hidden=query.include_hidden,
        ),
    ).rows
    items = [_player(row) for row in rows[: query.limit]]
    next_cursor = _encode_cursor(items[-1]) if len(rows) > query.limit else None
    return Page(items=items, next_cursor=next_cursor)


@router.get(
    "/players/{player_id:uuid}",
    response_model=PlayerRead,
    operation_id="roster_player_read",
)
def read_player(
    player_id: UUID,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> PlayerRead:
    """対象テナントの選手を 1 件返す。"""
    return _read_player(context, player_id)


@router.patch(
    "/players/{player_id:uuid}",
    response_model=PlayerRead,
    operation_id="roster_player_update",
)
def update_player(
    player_id: UUID,
    body: PlayerUpdate,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> PlayerRead:
    """指定された列だけを更新して選手を返す。"""
    if body.model_fields_set & {"roster_status_key", "roster_label_key"}:
        raise HTTPException(status_code=422)
    changes = tuple(body.model_dump(exclude_unset=True).items())
    if not changes:
        raise HTTPException(status_code=422)
    result = _run(context, PlayerUpdateToken(player_id, changes))
    if result.rows != ((1,),):
        raise HTTPException(status_code=404)
    return _read_player(context, player_id)
