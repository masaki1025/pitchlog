"""実tenantの有効球種をC2照合付きの有限ページで供給する。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from pitchlog.api.schemas.base import Page
from pitchlog.api.schemas.games import encode_preparation_options_cursor
from pitchlog.api.schemas.pitch_type_options import (
    PitchTypeOption,
    PitchTypeOptionsRequest,
)
from pitchlog.api.tenant_access import TenantMatchedRoute, require_tenant_access
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.pitch_type_options import PitchTypeOptionsToken
from pitchlog.repositories.transaction import (
    _TenantTransaction,
    tenant_transaction_scope,
)

router = APIRouter(tags=["球種"], route_class=TenantMatchedRoute)


def read_pitch_type_options(
    scope: _TenantTransaction, query: PitchTypeOptionsRequest
) -> Page[PitchTypeOption]:
    """真正scopeにだけ固定tokenを渡し、実読取行を閉DTOへ写す。"""
    if (
        type(scope) is not _TenantTransaction
        or type(query) is not PitchTypeOptionsRequest
    ):
        raise TypeError("束縛済みscopeと球種ページ要求が必要")
    query = PitchTypeOptionsRequest.model_validate(query.model_dump())
    rows = scope.run(PitchTypeOptionsToken(query.limit, query.cursor)).rows
    if len(rows) > query.limit + 1 or any(len(row) != 2 for row in rows):
        raise ValueError("球種ページの結果形が不正")
    supplied = [
        PitchTypeOption.model_validate({"key": row[0], "display_name": row[1]})
        for row in rows
    ]
    if any(a.key >= b.key for a, b in zip(supplied, supplied[1:])):
        raise ValueError("球種ページの順序が不正")
    items = supplied[: query.limit]
    return Page[PitchTypeOption](
        items=items,
        next_cursor=(
            encode_preparation_options_cursor(items[-1].key)
            if len(rows) > query.limit
            else None
        ),
    )


@router.get(
    "/vocabularies/pitch-types",
    response_model=Page[PitchTypeOption],
    operation_id="pitch_type_options",
)
def pitch_type_options(
    query: Annotated[PitchTypeOptionsRequest, Query()],
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> Page[PitchTypeOption]:
    """実認証されたtenant内だけの球種を1ページ返す。"""
    try:
        with tenant_transaction_scope(context) as scope:
            return read_pitch_type_options(scope, query)
    except Exception:
        raise HTTPException(status_code=503) from None
