"""API アプリケーションの構成を検証する。"""

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
async def test_routers_register_only_health_route() -> None:
    """静的ルータ登録から得られる経路が health だけであることを確認する。"""
    routes = tuple(
        route
        for router in api_app.ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute)
    )

    assert tuple(route.path for route in routes) == ("/health",)


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
