"""メタ情報の API 経路を定義する。"""

from fastapi import APIRouter

from pitchlog.api.schemas.base import HealthResponse

router = APIRouter(tags=["メタ情報"])


@router.get(
    "/health",
    response_model=HealthResponse,
    operation_id="meta_health_read",
    summary="ヘルスチェック",
)
async def health() -> HealthResponse:
    """ヘルスチェックの応答を返す。"""
    return HealthResponse(status="ok")
