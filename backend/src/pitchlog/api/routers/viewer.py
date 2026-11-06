"""同チームの閲覧端末向け、確定版の軽量な変化通知。"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from pitchlog.api.tenant_access import TenantMatchedRoute, require_tenant_access
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.transaction import tenant_transaction_scope
from pitchlog.repositories.viewer_probe import (
    ViewerProbeNotVisible,
    read_viewer_probe,
)

router = APIRouter(tags=["閲覧"], route_class=TenantMatchedRoute)


class ViewerHead(BaseModel):
    """確定値GETの必要性だけを伝える版。表示内容は含まない。"""

    model_config = ConfigDict(extra="forbid")
    status: Literal["in_progress", "finished"]
    generation: str
    watermark: str


@router.get(
    "/games/{game_id}/viewer-head",
    response_model=ViewerHead,
    operation_id="game_viewer_head",
)
def read_game_viewer_head(
    game_id: UUID,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> ViewerHead:
    """C2付きtenant読取のみ。記録端末や記録権の有無を要求しない。"""
    try:
        with tenant_transaction_scope(context) as scope:
            value = read_viewer_probe(scope, game_id)
    except ViewerProbeNotVisible:
        raise HTTPException(status_code=404) from None
    except Exception:
        raise HTTPException(status_code=503) from None
    return ViewerHead(
        status=value.status,
        generation=str(value.generation),
        watermark=str(value.watermark),
    )
