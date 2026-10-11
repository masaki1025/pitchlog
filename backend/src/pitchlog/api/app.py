"""FastAPI アプリケーションの生成機構を提供する。"""

import os

from fastapi import APIRouter, FastAPI
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pitchlog.api.errors import register_exception_handlers
from pitchlog.api.routers import auth, meta, players, team_records
from pitchlog.authz.signing_key_config import require_signing_key_configuration
from pitchlog.authz.token_presentation import TokenPresentation
from pitchlog.authz.verified_tenant import _activate_presentation

ROUTERS: tuple[APIRouter, ...] = (
    meta.router,
    auth.router,
    players.router,
    team_records.router,
)
_SIGNING_KEY_VARIABLE = "PITCHLOG_TOKEN_SIGNING_KEY_B64"


class _RenewedCookieMiddleware:
    """認証後の例外応答へ Cookie 更新ヘッダを引き継ぐ。"""

    def __init__(self, app: ASGIApp) -> None:
        """内側の ASGI アプリケーションを保持する。"""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """応答開始時に認証依存関数のヘッダを補う。"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_cookie(message: Message) -> None:
            if message["type"] == "http.response.start" and message["status"] != 401:
                cookie = scope.get("state", {}).get("renewed_cookie")
                headers = message.get("headers", [])
                if isinstance(cookie, str) and not any(
                    name.lower() == b"set-cookie" for name, _ in headers
                ):
                    message["headers"] = [
                        *headers,
                        (b"set-cookie", cookie.encode("latin-1")),
                    ]
            await send(message)

        await self.app(scope, receive, send_with_cookie)


def create_app() -> FastAPI:
    """共通設定を適用した FastAPI アプリケーションを作る。

    Returns:
        例外ハンドラと静的列挙したルータを登録済みのアプリケーション。
    """
    signing_key = require_signing_key_configuration(
        _SIGNING_KEY_VARIABLE,
        os.environ.get(_SIGNING_KEY_VARIABLE),
    )
    app = FastAPI(
        title="Pitchlog API",
        version=meta.get_application_version(),
        description="Pitchlog の API を提供する。",
    )
    app.state.token_presentation = TokenPresentation(signing_key)
    app.add_middleware(_RenewedCookieMiddleware)
    register_exception_handlers(app)
    for router in ROUTERS:
        app.include_router(router)
    _activate_presentation(app.state.token_presentation)
    return app
