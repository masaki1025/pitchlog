"""ヘルスチェックエンドポイントを検証するテスト。"""

import base64
import secrets
from importlib import import_module

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.anyio
async def test_health_returns_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """ヘルスチェックが正常な応答を返すことを確認する。"""
    encoded_key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    monkeypatch.setenv("PITCHLOG_TOKEN_SIGNING_KEY_B64", encoded_key)
    app = import_module("pitchlog.main").app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
