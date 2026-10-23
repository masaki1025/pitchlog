"""準備中試合の保存値をtenant限定で取得する。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from pitchlog.api.schemas.base import Page
from pitchlog.api.schemas.games import (
    PreparationOptionsRequest,
    PreparingGameCreate,
    PreparingGameListRequest,
    PreparingGamePreparationOptions,
    PreparingGameRead,
    _decode_preparing_snapshot,
    encode_preparing_game_cursor,
)
from pitchlog.api.tenant_access import TenantMatchedRoute, require_tenant_access
from pitchlog.db.game_state.rule_snapshot import encode_applied_rules
from pitchlog.repositories.context import TenantContext
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
