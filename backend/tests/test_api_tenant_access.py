"""保護された HTTP 応答の Cookie 更新を DB なしで検査する。"""

import base64
import secrets
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import fastapi.dependencies.utils
import fastapi.routing
import pytest
from httpx import ASGITransport, AsyncClient

from pitchlog.api.app import create_app
from pitchlog.api.routers import players
from pitchlog.repositories import tenant_context_issuance


@pytest.fixture(autouse=True)
def _configure_signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """各アプリへ独立した署名鍵を設定する。"""
    async def inline_call(function: Any, *args: Any, **kwargs: Any) -> Any:
        """隔離環境で同期経路をインライン実行する。"""
        return function(*args, **kwargs)

    monkeypatch.setattr(fastapi.dependencies.utils, "run_in_threadpool", inline_call)
    monkeypatch.setattr(fastapi.routing, "run_in_threadpool", inline_call)
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )


@pytest.mark.anyio
async def test_protected_request_renews_cookie_from_verified_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同じ提示値の期限が延びるたび応答 Cookie の Max-Age も伸びる。"""
    app = create_app()
    value = app.state.token_presentation.encode(uuid4())
    context = MagicMock()
    expires_at = [
        datetime.now(UTC) + timedelta(seconds=30),
        datetime.now(UTC) + timedelta(seconds=150),
    ]
    seen: list[tuple[str, object]] = []

    def issue(presented: str, presentation: object) -> tuple[MagicMock, datetime]:
        """照合済みの文脈と期限を返す。"""
        seen.append((presented, presentation))
        return context, expires_at.pop(0)

    monkeypatch.setattr(
        tenant_context_issuance, "issue_tenant_context_from_presented_token", issue
    )
    monkeypatch.setattr(players, "_run", lambda *_: SimpleNamespace(rows=()))
    headers = {"Cookie": f"__Host-pitchlog_token={value}"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        first = await client.get("/players?limit=1", headers=headers)
        second = await client.get("/players?limit=1", headers=headers)

    assert first.status_code == second.status_code == 200
    assert seen == [(value, app.state.token_presentation)] * 2
    ages: list[int] = []
    for response in (first, second):
        cookie = response.headers["set-cookie"]
        assert cookie.startswith(f"__Host-pitchlog_token={value};")
        assert "path=/" in cookie.lower()
        assert "secure" in cookie.lower()
        assert "httponly" in cookie.lower()
        assert "samesite=strict" in cookie.lower()
        assert "domain=" not in cookie.lower()
        ages.append(
            int(
                next(
                    part[8:]
                    for part in cookie.split("; ")
                    if part.startswith("Max-Age=")
                )
            )
        )
        assert value not in response.text
        assert value not in str(response.request.url)
    assert 28 <= ages[0] <= 30
    assert 148 <= ages[1] <= 150


@pytest.mark.anyio
async def test_requests_without_extension_do_not_set_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """公開経路と拒否した保護経路では Cookie を発行しない。"""
    app = create_app()
    value = app.state.token_presentation.encode(uuid4())
    monkeypatch.setattr(
        tenant_context_issuance,
        "issue_tenant_context_from_presented_token",
        lambda *_: None,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        public = await client.get("/health")
        missing = await client.get("/players?limit=1")
        rejected = await client.get(
            "/players?limit=1", headers={"Cookie": f"__Host-pitchlog_token={value}"}
        )

    assert public.status_code == 200
    assert missing.status_code == rejected.status_code == 401
    assert all(
        "set-cookie" not in response.headers for response in (public, missing, rejected)
    )


def test_issuer_preserves_verified_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    """文脈発行で DB の期限を落とさない。"""
    app = create_app()
    expiry = datetime.now(UTC) + timedelta(minutes=10)
    tenant_id = uuid4()
    engine = MagicMock()
    monkeypatch.setattr(
        tenant_context_issuance, "create_database_engine", lambda: engine
    )
    monkeypatch.setattr(
        tenant_context_issuance,
        "verify_tenant_id",
        lambda *_: (tenant_id, expiry),
    )
    issued = tenant_context_issuance.issue_tenant_context_from_presented_token(
        "opaque", app.state.token_presentation
    )

    assert issued is not None
    assert issued[0].tenant_id == tenant_id
    assert issued[1] is expiry
    engine.dispose.assert_called_once_with()
