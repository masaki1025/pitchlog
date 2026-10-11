"""API アプリケーションの構成を検証する。"""

import base64
import secrets
from importlib import metadata

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

import pitchlog.api.app as api_app


@pytest.fixture(autouse=True)
def _configure_signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """アプリ生成試験へ CSPRNG 由来の署名鍵を与える。"""
    encoded_key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    monkeypatch.setenv("PITCHLOG_TOKEN_SIGNING_KEY_B64", encoded_key)


@pytest.mark.anyio
async def test_routers_is_module_level_tuple() -> None:
    """ルータ登録がモジュールトップレベルのタプルであることを確認する。"""
    assert "ROUTERS" in vars(api_app)
    assert isinstance(api_app.ROUTERS, tuple)


@pytest.mark.anyio
async def test_routers_register_meta_login_player_and_team_routes() -> None:
    """静的登録したメタ情報・ログイン・選手・対戦相手の入口を照合する。"""
    routes = tuple(
        route
        for router in api_app.ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute)
    )

    assert tuple(
        (tuple(sorted(route.methods or ())), route.path) for route in routes
    ) == (
        (("GET",), "/health"),
        (("GET",), "/version"),
        (("POST",), "/auth/login"),
        (("POST",), "/auth/logout"),
        (("PATCH",), "/auth/password"),
        (("POST",), "/players"),
        (("GET",), "/players"),
        (("GET",), "/players/{player_id:uuid}"),
        (("PATCH",), "/players/{player_id:uuid}"),
        (("POST",), "/players/status-preview"),
        (("POST",), "/players/status-apply"),
        (("POST",), "/team-records"),
        (("GET",), "/team-records"),
        (("PATCH",), "/team-records/{team_record_id:uuid}"),
        (("DELETE",), "/team-records/{team_record_id:uuid}"),
    )
    assert tuple(route.operation_id for route in routes) == (
        "meta_health_read",
        "meta_version_read",
        "auth_login_create",
        "auth_logout_create",
        "auth_password_update",
        "roster_player_create",
        "roster_player_list",
        "roster_player_read",
        "roster_player_update",
        "roster_player_status_preview",
        "roster_player_status_apply",
        "roster_team_create",
        "roster_team_list",
        "roster_team_update",
        "roster_team_delete",
    )


@pytest.mark.anyio
async def test_create_app_returns_health_response() -> None:
    """生成関数が既存契約どおりの health 応答を返すことを確認する。"""
    transport = ASGITransport(app=api_app.create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.content == b'{"status":"ok"}'


@pytest.mark.anyio
async def test_create_app_returns_version_response() -> None:
    """生成関数がインストール済みのアプリケーション版を返すことを確認する。"""
    transport = ASGITransport(app=api_app.create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/version")

    application_version = metadata.version("pitchlog-backend")
    assert application_version == "0.1.0"
    assert response.status_code == 200
    assert response.json() == {"version": application_version}


@pytest.mark.anyio
async def test_create_app_registers_error_handlers() -> None:
    """生成関数がステップ 1 の例外ハンドラを登録することを確認する。"""
    transport = ASGITransport(app=api_app.create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {"error": {"message": "対象が見つかりません"}}


@pytest.mark.anyio
async def test_health_route_has_expected_operation_id() -> None:
    """ヘルスチェック経路が定めた operation ID を持つことを確認する。"""
    route = next(
        route
        for router in api_app.ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute) and route.path == "/health"
    )

    assert route.operation_id == "meta_health_read"


@pytest.mark.anyio
async def test_version_route_has_expected_operation_id() -> None:
    """版情報経路が定めた operation ID を持つことを確認する。"""
    route = next(
        route
        for router in api_app.ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute) and route.path == "/version"
    )

    assert route.operation_id == "meta_version_read"


def test_create_app_sets_openapi_metadata() -> None:
    """生成関数が OpenAPI メタ情報と既定の文書経路を設定することを確認する。"""
    app = api_app.create_app()

    assert app.title == "Pitchlog API"
    assert app.version == metadata.version("pitchlog-backend")
    assert app.description == "Pitchlog の API を提供する。"
    assert app.docs_url == "/docs"
    assert app.redoc_url == "/redoc"
    assert app.openapi_url == "/openapi.json"
