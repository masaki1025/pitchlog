"""同チーム閲覧端末へ非ロックの確定版と保存済み表示を返す。"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, TypeAdapter

from pitchlog.api.schemas.started_games import (
    StartedLineupPrefixGameRead,
    StartedNonplayPrefixGameRead,
)
from pitchlog.api.tenant_access import TenantMatchedRoute, require_tenant_access
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.game_lifecycle import _read_lifecycle_display
from pitchlog.repositories.ordinary_prefix_read import (
    OrdinaryPrefixView,
    read_viewer_prefix,
)
from pitchlog.repositories.started_read import StartedReadNotVisible
from pitchlog.repositories.transaction import started_snapshot_read_scope
from pitchlog.repositories.viewer_probe import (
    ViewerProbeNotVisible,
    read_viewer_probe,
)

router = APIRouter(tags=["閲覧"], route_class=TenantMatchedRoute)


class ViewerHead(BaseModel):
    """確定値GETの必要性だけを伝える版。表示内容は含まない。"""

    model_config = ConfigDict(extra="forbid")
    status: Literal["in_progress", "finished"]
    version: str
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
        with started_snapshot_read_scope(context) as scope:
            value = read_viewer_probe(scope, game_id)
    except ViewerProbeNotVisible:
        raise HTTPException(status_code=404) from None
    except Exception:
        raise HTTPException(status_code=503) from None
    return ViewerHead(
        status=value.status,
        version=value.version,
        watermark=str(value.watermark),
    )


@router.get(
    "/games/{game_id}/viewer",
    response_model=StartedLineupPrefixGameRead | StartedNonplayPrefixGameRead,
    operation_id="game_viewer_saved",
)
def read_game_viewer_saved(
    game_id: UUID,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
    expected_version: Annotated[str, Query(pattern=r"^ve1_[a-f0-9]{64}$")],
    limit: Annotated[int, Query(ge=1, le=25)] = 25,
    cursor: Annotated[str | None, Query(min_length=1, max_length=2048)] = None,
) -> Response:
    """RR READ ONLYの同一snapshotから保存CPと有限pageだけを返す。"""
    try:
        with started_snapshot_read_scope(context) as scope:
            head = read_viewer_probe(scope, game_id)
            if expected_version != head.version:
                raise RuntimeError("閲覧本文の実効版が不一致")
            read = read_viewer_prefix(scope, game_id, limit=limit, cursor=cursor)
            if type(read) is StartedReadNotVisible:
                raise ViewerProbeNotVisible
            if type(read) is not OrdinaryPrefixView:
                raise RuntimeError("閲覧原本が不正")
            from pitchlog.api.routers.started_games import _read

            metadata = _read(read.metadata).model_dump(mode="python", by_alias=True)
            projected = dict(read.projection)
            if projected.get("profile") == "nonplay-prefix-read-v1":
                display = _read_lifecycle_display(scope, game_id)
                if type(display) is not dict or display.get("status") != head.status:
                    raise RuntimeError("閲覧終了版が不一致")
                if projected["checkpoint"].content.d3 != str(head.watermark):
                    raise RuntimeError("閲覧D3が不一致")
                packet = {
                    **metadata,
                    **projected,
                    "read_kind": "nonplay-prefix",
                    "status": head.status,
                    "lifecycle": display,
                }
                model = StartedNonplayPrefixGameRead
            else:
                if head.status != "in_progress":
                    raise RuntimeError("終了状態にv3原本")
                if projected["prefix_ref"].length != str(head.watermark):
                    raise RuntimeError("閲覧D3が不一致")
                page = dict(projected["page"])
                page["items"] = [
                    {
                        **item,
                        "play_runners": [
                            {
                                k: v
                                for k, v in runner.items()
                                if k
                                not in {"tenant_id", "import_batch_id", "retired_at"}
                            }
                            for runner in item.get("play_runners", [])
                        ],
                    }
                    for item in page["items"]
                ]
                projected["page"] = page
                packet = {**metadata, **projected, "read_kind": "lineup-prefix"}
                model = StartedLineupPrefixGameRead
            validated = model.model_validate_json(
                TypeAdapter(dict).dump_json(packet, by_alias=True, exclude_unset=True)
            )
            if read_viewer_probe(scope, game_id) != head:
                raise RuntimeError("閲覧本文と実効版が不一致")
            return Response(
                validated.model_dump_json(by_alias=True, exclude_unset=True),
                media_type="application/json",
            )
    except ViewerProbeNotVisible:
        raise HTTPException(status_code=404) from None
    except Exception:
        raise HTTPException(status_code=503) from None
