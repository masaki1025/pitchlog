"""API アプリケーションの構成を検証する。"""

from importlib import metadata

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

import pitchlog.api.app as api_app


@pytest.mark.anyio
async def test_routers_is_module_level_tuple() -> None:
    """ルータ登録がモジュールトップレベルのタプルであることを確認する。"""
    assert "ROUTERS" in vars(api_app)
    assert isinstance(api_app.ROUTERS, tuple)


@pytest.mark.anyio
async def test_routers_register_only_meta_routes() -> None:
    """静的ルータ登録から得られる経路がメタ情報だけであることを確認する。"""
    routes = tuple(
        route
        for router in api_app.ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute)
    )

    assert tuple(route.path for route in routes) == ("/health", "/version")


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
