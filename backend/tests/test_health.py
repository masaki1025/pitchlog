"""ヘルスチェックエンドポイントを検証するテスト。"""

import pytest
from httpx import ASGITransport, AsyncClient

from pitchlog.main import app


@pytest.mark.anyio
async def test_health_returns_ok() -> None:
    """ヘルスチェックが正常な応答を返すことを確認する。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
