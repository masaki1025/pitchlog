"""API 器が非コアの規約を守ることを検証する。"""

import json
from pathlib import Path
from typing import Final

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from pitchlog.api.app import ROUTERS, create_app
from pitchlog.api.schemas.base import ErrorDetail, ErrorEnvelope, ErrorField

_REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_API_SOURCE_ROOT: Final[Path] = (
    _REPOSITORY_ROOT / "backend" / "src" / "pitchlog" / "api"
)
_ROUTE_REGISTRY_PATH: Final[Path] = (
    _REPOSITORY_ROOT / "contracts" / "authz" / "route-registry.json"
)
_DATABASE_TERMS: Final[tuple[str, ...]] = (
    "sqlalchemy",
    "Session",
    "engine",
    "session.execute",
    "select(",
    "text(",
    "raw_connection",
)
_SYNCHRONIZATION_TERMS: Final[tuple[str, ...]] = (
    "idempotenc",
    "seq_no",
    "tombstone",
    "revision_no",
    "generation",
)
_REQUEST_ACCESS_PATTERNS: Final[tuple[str, ...]] = (
    "request.headers",
    "request.body",
    "request.query_params",
    "cookies",
)


def _api_source_files() -> tuple[Path, ...]:
    """API 配下の Python ソースファイルを列挙する。

    Returns:
        検査対象のソースファイル。
    """
    assert _API_SOURCE_ROOT.is_dir()
    source_files = tuple(sorted(_API_SOURCE_ROOT.rglob("*.py")))
    assert source_files
    return source_files


def _api_source_text() -> str:
    """API 配下の Python ソースを連結して返す。

    Returns:
        検査対象の全ソーステキスト。
    """
    return "\n".join(
        source_file.read_text(encoding="utf-8") for source_file in _api_source_files()
    )


def _router_routes() -> tuple[APIRoute, ...]:
    """静的登録したルータから API 経路を抽出する。

    Returns:
        静的登録した API 経路。
    """
    return tuple(
        route
        for router in ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute)
    )


def _registry_operation_ids() -> set[str]:
    """認可経路レジストリの操作識別子を取得する。

    Returns:
        認可経路レジストリに定義された操作識別子。
    """
    assert _ROUTE_REGISTRY_PATH.is_file()
    registry = json.loads(_ROUTE_REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(registry, dict)
    enums = registry.get("enums")
    assert isinstance(enums, dict)
    operation_ids = enums.get("operation_ids")
    assert isinstance(operation_ids, list)
    assert all(isinstance(operation_id, str) for operation_id in operation_ids)
    return {
        operation_id for operation_id in operation_ids if isinstance(operation_id, str)
    }


def test_api_source_has_no_database_terms() -> None:
    """API ソースにデータベース接続の語彙が無いことを確認する。"""
    source_text = _api_source_text()

    assert all(term not in source_text for term in _DATABASE_TERMS)


def test_api_source_has_no_synchronization_terms() -> None:
    """API ソースに同期セマンティクスの語彙が無いことを確認する。"""
    source_text = _api_source_text()

    assert all(term not in source_text for term in _SYNCHRONIZATION_TERMS)


@pytest.mark.anyio
async def test_forbidden_response_is_hidden_as_not_found() -> None:
    """403 が 404 と完全に同一の本文へ写ることを確認する。"""
    app = create_app()

    @app.get("/forbidden")
    async def raise_forbidden() -> None:
        """403 の HTTP 例外を送出する。"""
        raise HTTPException(status_code=403)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        not_found_response = await client.get("/missing")
        forbidden_response = await client.get("/forbidden")

    assert forbidden_response.status_code == 404
    assert forbidden_response.content == not_found_response.content


def test_router_routes_are_only_meta_routes() -> None:
    """静的登録した API 経路がメタ情報の 2 本だけであることを確認する。"""
    routes = _router_routes()

    assert len(routes) == 2
    assert {route.path for route in routes} == {"/health", "/version"}
    assert all(route.response_model is not None for route in routes)


def test_error_envelope_models_have_no_code_field() -> None:
    """エラー封筒と入れ子モデルが理由コードを持たないことを確認する。"""
    error_models = (ErrorEnvelope, ErrorDetail, ErrorField)

    assert all("code" not in error_model.model_fields for error_model in error_models)


def test_api_operation_ids_do_not_overlap_authz_registry() -> None:
    """API の operation ID が認可経路レジストリと重ならないことを確認する。"""
    routes = _router_routes()
    assert all(route.operation_id is not None for route in routes)
    operation_ids = {
        route.operation_id for route in routes if route.operation_id is not None
    }

    assert operation_ids.isdisjoint(_registry_operation_ids())


def test_error_handlers_do_not_access_request_data() -> None:
    """例外ハンドラが要求の機密情報を参照しないことを確認する。"""
    error_source_path = _API_SOURCE_ROOT / "errors.py"
    assert error_source_path.is_file()
    source_text = error_source_path.read_text(encoding="utf-8")

    assert all(pattern not in source_text for pattern in _REQUEST_ACCESS_PATTERNS)
