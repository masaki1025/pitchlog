"""実認証/C2とtenant scopeから有効打球語彙を有限読取する。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from pitchlog.api.schemas.base import Page
from pitchlog.api.schemas.batted_ball_options import (
    BattedBallOption,
    BattedBallOptionsRequest,
)
from pitchlog.api.schemas.games import (
    decode_preparation_options_cursor,
    encode_preparation_options_cursor,
)
from pitchlog.api.tenant_access import TenantMatchedRoute, require_tenant_access
from pitchlog.repositories.batted_ball_options import BattedBallOptionsToken
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.repositories.transaction import (
    _TenantTransaction,
    tenant_transaction_scope,
)

router = APIRouter(tags=["打球語彙"], route_class=TenantMatchedRoute)


def read_batted_ball_options(
    scope: _TenantTransaction, query: BattedBallOptionsRequest
) -> Page[BattedBallOption]:
    """真正scopeに固定tokenを渡し、順序とページ上限を閉検証する。"""
    if (
        type(scope) is not _TenantTransaction
        or type(query) is not BattedBallOptionsRequest
    ):
        raise TypeError("束縛済みscopeと打球語彙ページ要求が必要")
    query = BattedBallOptionsRequest.model_validate(query.model_dump())
    cursor = decode_preparation_options_cursor(query.cursor) if query.cursor else ""
    result = scope.run_function(BattedBallOptionsToken(query.limit, cursor))
    if type(result) is not TenantOperationResult or type(result.rows) is not tuple:
        raise ValueError("打球語彙ページの結果型が不正")
    rows = result.rows
    if len(rows) > query.limit + 1 or any(
        type(row) is not tuple or len(row) != 2 for row in rows
    ):
        raise ValueError("打球語彙ページの結果形が不正")
    supplied = [
        BattedBallOption.model_validate({"key": row[0], "display_name": row[1]})
        for row in rows
    ]
    if any(a.key >= b.key for a, b in zip(supplied, supplied[1:])) or any(
        item.key <= cursor for item in supplied
    ):
        raise ValueError("打球語彙ページの順序が不正")
    items = supplied[: query.limit]
    return Page[BattedBallOption](
        items=items,
        next_cursor=(
            encode_preparation_options_cursor(items[-1].key)
            if len(rows) > query.limit
            else None
        ),
    )


@router.get(
    "/vocabularies/batted-balls",
    response_model=Page[BattedBallOption],
    operation_id="batted_ball_options",
)
def batted_ball_options(
    query: Annotated[BattedBallOptionsRequest, Query()],
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> Page[BattedBallOption]:
    """認証とtenant照合後の実要求だけを実scopeへ渡す。"""
    try:
        with tenant_transaction_scope(context) as scope:
            return read_batted_ball_options(scope, query)
    except Exception:
        raise HTTPException(status_code=503) from None
