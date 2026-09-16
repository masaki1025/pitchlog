"""メタ情報の API 経路を定義する。"""

from importlib import metadata

from fastapi import APIRouter

from pitchlog.api.schemas.base import HealthResponse, VersionResponse

router = APIRouter(tags=["メタ情報"])


def get_application_version() -> str:
    """インストール済みパッケージからアプリケーション版を取得する。

    Returns:
        アプリケーションの版。
    """
    return metadata.version("pitchlog-backend")


@router.get(
    "/health",
    response_model=HealthResponse,
    operation_id="meta_health_read",
    summary="ヘルスチェック",
)
async def health() -> HealthResponse:
    """ヘルスチェックの応答を返す。"""
    return HealthResponse(status="ok")


@router.get(
    "/version",
    response_model=VersionResponse,
    operation_id="meta_version_read",
    summary="アプリケーションの版情報",
)
async def read_version() -> VersionResponse:
    """アプリケーション版の応答を返す。"""
    return VersionResponse(version=get_application_version())
