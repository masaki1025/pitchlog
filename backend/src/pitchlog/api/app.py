"""FastAPI アプリケーションの生成機構を提供する。"""

import os
from pathlib import Path

from fastapi import APIRouter, FastAPI
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pitchlog.api.errors import register_exception_handlers
from pitchlog.api.routers import (
    auth,
    games,
    lineup_memory,
    meta,
    pitch_type_options,
    players,
    started_games,
    sync,
    team_records,
)
from pitchlog.api.tenant_access import tenant_match_response_headers
from pitchlog.authz.signing_key_config import require_signing_key_configuration
from pitchlog.authz.token_presentation import TokenPresentation
from pitchlog.authz.verified_tenant import _activate_presentation
from pitchlog.domainrt import verify_domain_artifact
from pitchlog.recording_rights.rg1_lifecycle import configure_runtime

ROUTERS: tuple[APIRouter, ...] = (
    meta.router,
    auth.router,
    players.router,
    team_records.router,
    lineup_memory.router,
    games.router,
    pitch_type_options.router,
    started_games.router,
    sync.router,
)
_SIGNING_KEY_VARIABLE = "PITCHLOG_TOKEN_SIGNING_KEY_B64"
_RG1_CLIENT_CONFIG_PATH = Path("/run/pitchlog/rg1-client.json")
_BINDING_CLIENT_VARIABLE = "PITCHLOG_BINDING_CLIENT_CONFIG"


class _RenewedCookieMiddleware:
    """Cookie 更新を引き継ぎ、Cookie 付き応答の保存を禁止する。"""

    def __init__(self, app: ASGIApp) -> None:
        """内側の ASGI アプリケーションを保持する。"""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """応答開始時に Cookie とキャッシュ指示のヘッダを補う。"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_cookie(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if message["status"] != 401:
                    cookie = scope.get("state", {}).get("renewed_cookie")
                    if isinstance(cookie, str) and not any(
                        name.lower() == b"set-cookie" for name, _ in headers
                    ):
                        headers.append((b"set-cookie", cookie.encode("latin-1")))
                if any(name.lower() == b"set-cookie" for name, _ in headers):
                    message["headers"] = [
                        (name, value)
                        for name, value in headers
                        if name.lower() != b"cache-control"
                    ] + [(b"cache-control", b"no-store")]
                message["headers"] = tenant_match_response_headers(
                    scope, message["status"], list(message.get("headers", headers))
                )
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
    configure_runtime(
        _RG1_CLIENT_CONFIG_PATH if _RG1_CLIENT_CONFIG_PATH.exists() else None
    )
    # CI では Node の版を揃えないため、ここでは artifact だけを照合する。
    # Node の起動と版の照合は domainrt のホストを開くときに行う。
    verify_domain_artifact()
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
    configured = os.environ.get(_BINDING_CLIENT_VARIABLE)
    app.state.binding_client_config_path = (
        Path(configured) if configured else None
    )
    _activate_presentation(app.state.token_presentation)
    return app
