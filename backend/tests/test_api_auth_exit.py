"""ログアウトと PW 変更の HTTP 契約を DB なしで検査する。"""

import base64
import secrets
from collections.abc import Callable
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from pitchlog.api.app import create_app
from pitchlog.api.routers import auth

_COOKIE = "__Host-pitchlog_token=presented"
_GATE_HEADERS = {
    "Cookie": _COOKIE,
    "X-Pitchlog-Request": "1",
    "Origin": "https://test",
}
_PASSWORDS = {"current_password": "current", "new_password": "new"}


@pytest.fixture(autouse=True)
def _configure_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """試験用署名鍵と許可オリジンを設定する。"""

    async def run_inline(call: Callable[[], object]) -> object:
        """境界呼び出しを試験内で実行する。"""
        return call()

    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )
    monkeypatch.setenv("PITCHLOG_ALLOWED_ORIGINS", "https://test")
    monkeypatch.setattr(auth, "run_in_threadpool", run_inline)


@pytest.mark.anyio
async def test_logout_calls_boundary_and_clears_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """既存の失効関数を呼び、Cookie を即時削除する。"""
    called = MagicMock()
    resource = object()
    monkeypatch.setattr(auth, "logout_token", called)
    monkeypatch.setattr(auth, "get_login_connection", lambda: resource)
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        result = await client.post("/auth/logout", headers=_GATE_HEADERS)

    assert result.status_code == 200
    assert result.json() == {"status": "logged_out"}
    assert "presented" not in result.text
    assert "Max-Age=0" in result.headers["set-cookie"]
    assert '__Host-pitchlog_token=""' in result.headers["set-cookie"]
    assert "Secure" in result.headers["set-cookie"]
    assert "HttpOnly" in result.headers["set-cookie"]
    called.assert_called_once_with("presented", app.state.token_presentation, resource)


@pytest.mark.anyio
async def test_password_change_requires_current_password_and_clears_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """現行 PW 必須で、成功時には新しい提示値を返さない。"""
    called = MagicMock(return_value=True)
    resource = object()
    monkeypatch.setattr(auth, "change_password_token", called)
    monkeypatch.setattr(auth, "get_login_connection", lambda: resource)
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        missing = await client.patch(
            "/auth/password", json={"new_password": "new"}, headers=_GATE_HEADERS
        )
        result = await client.patch(
            "/auth/password", json=_PASSWORDS, headers=_GATE_HEADERS
        )

    assert missing.status_code == 422
    assert result.status_code == 200
    assert result.json() == {"status": "password_changed"}
    assert "presented" not in result.text
    assert "new" not in result.text
    assert "Max-Age=0" in result.headers["set-cookie"]
    assert '__Host-pitchlog_token=""' in result.headers["set-cookie"]
    called.assert_called_once_with(
        "presented", "current", "new", app.state.token_presentation, resource
    )


@pytest.mark.anyio
async def test_password_failures_have_identical_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DB が返す全拒否理由を 1 つの本文へまとめる。"""
    monkeypatch.setattr(auth, "change_password_token", lambda *_args: False)
    monkeypatch.setattr(auth, "get_login_connection", object)
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        first = await client.patch(
            "/auth/password", json=_PASSWORDS, headers=_GATE_HEADERS
        )
        second = await client.patch(
            "/auth/password",
            json={"current_password": "wrong", "new_password": "invalid"},
            headers=_GATE_HEADERS,
        )

    assert first.status_code == second.status_code == 401
    assert first.content == second.content
    assert first.json() == {"error": {"message": "認証情報がありません"}}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path,method", [("/auth/logout", "post"), ("/auth/password", "patch")]
)
async def test_mutating_routes_use_existing_request_gate(
    path: str, method: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """提示値や CSRF 条件が足りなければ実体を呼ばない。"""
    called = MagicMock()
    monkeypatch.setattr(auth, "logout_token", called)
    monkeypatch.setattr(auth, "change_password_token", called)
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        request = getattr(client, method)
        missing = await request(path, json=_PASSWORDS)
        bad_csrf = await request(path, json=_PASSWORDS, headers={"Cookie": _COOKIE})

    assert missing.status_code == 401
    assert bad_csrf.status_code == 403
    called.assert_not_called()
