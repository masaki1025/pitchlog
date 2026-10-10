"""対戦相手チームレコードの登録・一覧・変更・削除の入口。"""

import base64
import binascii
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query

from pitchlog.api.errors import TeamRecordDeleteBlocked
from pitchlog.api.schemas.base import Page
from pitchlog.api.schemas.roster import (
    ROSTER_PAGE_SIZE_MAX,
    TeamRecordCreate,
    TeamRecordCreated,
    TeamRecordListRequest,
    TeamRecordRead,
    TeamRecordUpdate,
)
from pitchlog.api.tenant_access import require_tenant_access
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.roster import (
    GameTeamLinkReadToken,
    PlayerReadToken,
    TeamRecordCreateToken,
    TeamRecordDeleteToken,
    TeamRecordReadToken,
    TeamRecordUpdateToken,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.repositories.transaction import tenant_transaction_scope

router = APIRouter(tags=["対戦相手チーム"])
_TEAM_FIELDS = ("id", "kind", "name", "hidden_at")


def _run(
    context: TenantContext, operation: TenantOperationToken
) -> TenantOperationResult:
    """登録済みの単一操作を実行する。"""
    with tenant_transaction_scope(context) as scope:
        return scope.run(operation)


def _team(row: tuple[object, ...]) -> TeamRecordRead:
    """読み取り結果を応答 DTO へ写す。"""
    return TeamRecordRead.model_validate(dict(zip(_TEAM_FIELDS, row, strict=True)))


def _read_team(context: TenantContext, team_record_id: UUID) -> TeamRecordRead:
    """対象テナントの公開中の対戦相手を取得する。"""
    rows = _run(context, TeamRecordReadToken(limit=1, record_id=team_record_id)).rows
    if not rows:
        raise HTTPException(status_code=404)
    return _team(rows[0])


def _decode_cursor(cursor: str | None) -> UUID | None:
    """不透明なページ位置を識別子に戻す。"""
    if cursor is None:
        return None
    try:
        encoded = cursor + "=" * (-len(cursor) % 4)
        value = base64.b64decode(encoded, altchars=b"-_", validate=True).decode("ascii")
        if len(value) != 32:
            raise ValueError
        return UUID(hex=value)
    except (binascii.Error, UnicodeError, ValueError):
        raise HTTPException(status_code=422) from None


def _encode_cursor(team: TeamRecordRead) -> str:
    """次のページ位置を不透明な値にする。"""
    return (
        base64.urlsafe_b64encode(team.id.hex.encode("ascii"))
        .decode("ascii")
        .rstrip("=")
    )


@router.post(
    "/team-records",
    response_model=TeamRecordCreated,
    status_code=201,
    operation_id="roster_team_create",
)
def create_team_record(
    body: TeamRecordCreate,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> TeamRecordCreated:
    """登録を完了してから同じ名前の警告を返す。"""
    team_id = uuid4()
    _run(context, TeamRecordCreateToken(team_id, body.name))
    created = _read_team(context, team_id)
    similar = _run(
        context,
        TeamRecordReadToken(
            limit=ROSTER_PAGE_SIZE_MAX,
            similar_name=body.name,
            exclude_id=team_id,
        ),
    ).rows
    return TeamRecordCreated.model_validate(
        created.model_dump()
        | {"similar_names": [_team(row).name for row in similar[:ROSTER_PAGE_SIZE_MAX]]}
    )


@router.get(
    "/team-records",
    response_model=Page[TeamRecordRead],
    operation_id="roster_team_list",
)
def list_team_records(
    query: Annotated[TeamRecordListRequest, Query()],
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> Page[TeamRecordRead]:
    """対象テナントの対戦相手を上限付きで一覧する。"""
    rows = _run(
        context,
        TeamRecordReadToken(
            limit=query.limit,
            cursor_id=_decode_cursor(query.cursor),
            include_hidden=query.include_hidden,
        ),
    ).rows
    items = [_team(row) for row in rows[: query.limit]]
    return Page(
        items=items,
        next_cursor=_encode_cursor(items[-1]) if len(rows) > query.limit else None,
    )


@router.patch(
    "/team-records/{team_record_id:uuid}",
    response_model=TeamRecordRead,
    operation_id="roster_team_update",
)
def update_team_record(
    team_record_id: UUID,
    body: TeamRecordUpdate,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> TeamRecordRead:
    """対象テナントの対戦相手の名前を変更する。"""
    if "name" not in body.model_fields_set or body.name is None:
        raise HTTPException(status_code=422)
    changed = _run(context, TeamRecordUpdateToken(team_record_id, name=body.name))
    if changed.rows != ((1,),):
        raise HTTPException(status_code=404)
    return _read_team(context, team_record_id)


@router.api_route(
    "/team-records/{team_record_id:uuid}",
    methods=["DELETE"],
    response_model=TeamRecordRead,
    operation_id="roster_team_delete",
)
def delete_team_record(
    team_record_id: UUID,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> TeamRecordRead:
    """参照の有無を確認し、参照されない対戦相手だけを非表示にする。"""
    with tenant_transaction_scope(context) as scope:
        existing = scope.run(TeamRecordReadToken(limit=1, record_id=team_record_id))
        if not existing.rows:
            raise HTTPException(status_code=404)
        if scope.run(GameTeamLinkReadToken(team_record_id)).rows:
            raise TeamRecordDeleteBlocked("games")
        if scope.run(
            PlayerReadToken(limit=1, team_record_id=team_record_id, include_hidden=True)
        ).rows:
            raise TeamRecordDeleteBlocked("players")
        hidden_at = datetime.now(timezone.utc)
        changed = scope.run(TeamRecordDeleteToken(team_record_id, hidden_at))
        if changed.rows != ((1,),):
            raise HTTPException(status_code=404)
        return _team(existing.rows[0]).model_copy(update={"hidden_at": hidden_at})
