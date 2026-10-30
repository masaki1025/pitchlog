"""API アプリケーションの構成を検証する。"""

import base64
from importlib import metadata
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

import pitchlog.api.app as api_app
import pitchlog.domainrt.host as domainrt_host
from pitchlog.domainrt import DomainRuntimeError

_REAL_DOMAIN_DIR = Path(__file__).resolve().parents[2] / "frontend/public/domain"


@pytest.fixture(autouse=True)
def _configure_signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """アプリ生成試験へ既存の非秘密固定試験素材を与える。"""
    encoded_key = base64.b64encode(b"r" * 32).decode("ascii")
    monkeypatch.setenv("PITCHLOG_TOKEN_SIGNING_KEY_B64", encoded_key)


@pytest.fixture
def isolated_domain_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    """製品の固定相対パスに実 artifact の一時コピーを置く。"""
    directory = tmp_path / "frontend/public/domain"
    directory.mkdir(parents=True)
    artifact = directory / "pitchlog-domain.js"
    declaration = directory / "pitchlog-domain.json"
    for destination in (artifact, declaration):
        destination.write_bytes((_REAL_DOMAIN_DIR / destination.name).read_bytes())
    monkeypatch.setattr(domainrt_host, "_product_root", lambda: tmp_path)
    return artifact, declaration


@pytest.mark.anyio
async def test_routers_is_module_level_tuple() -> None:
    """ルータ登録がモジュールトップレベルのタプルであることを確認する。"""
    assert "ROUTERS" in vars(api_app)
    assert isinstance(api_app.ROUTERS, tuple)


@pytest.mark.anyio
async def test_routers_register_meta_auth_player_and_team_routes() -> None:
    """静的登録したメタ情報・認証・選手・対戦相手の入口を照合する。"""
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
        (("GET",), "/auth/session"),
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
        (("GET",), "/team-records/self"),
        (("PATCH",), "/team-records/{team_record_id:uuid}"),
        (("DELETE",), "/team-records/{team_record_id:uuid}"),
        (("GET",), "/team-records/{team_record_id:uuid}/lineup-memory"),
        (("GET",), "/games"),
        (("GET",), "/games/preparation-options"),
        (("POST",), "/games"),
        (("GET",), "/games/{game_id}"),
        (("POST",), "/devices/enroll"),
        (("POST",), "/games/{game_id}/start"),
        (("POST",), "/games/{game_id}/start/resolve"),
        (("GET",), "/vocabularies/pitch-types"),
        (("GET",), "/games/{game_id}/started"),
        (("POST",), "/games/{game_id}/sync/events"),
    )
    assert tuple(route.operation_id for route in routes) == (
        "meta_health_read",
        "meta_version_read",
        "auth_login_create",
        "auth_session_read",
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
        "roster_self_team_read",
        "roster_team_update",
        "roster_team_delete",
        "lineup_memory_read",
        "preparing_game_list",
        "preparing_game_preparation_options",
        "preparing_game_create",
        "preparing_game_detail",
        "initial_device_enroll",
        "initial_game_start",
        "initial_game_start_resolve",
        "pitch_type_options",
        "started_game_detail",
        "sync_events",
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


def test_create_app_rejects_missing_domain_artifact(
    isolated_domain_artifact: tuple[Path, Path],
) -> None:
    """① artifact 不在ならアプリ生成前に失敗する。"""
    artifact, _ = isolated_domain_artifact
    artifact.unlink()

    with pytest.raises(DomainRuntimeError) as caught:
        api_app.create_app()

    assert caught.value.code == "ARTIFACT_UNAVAILABLE"


def test_create_app_rejects_domain_hash_mismatch(
    isolated_domain_artifact: tuple[Path, Path],
) -> None:
    """② artifact のハッシュ不一致ならアプリ生成前に失敗する。"""
    artifact, _ = isolated_domain_artifact
    artifact.write_bytes(artifact.read_bytes() + b"changed")

    with pytest.raises(DomainRuntimeError) as caught:
        api_app.create_app()

    assert caught.value.code == "HASH_MISMATCH"


@pytest.mark.parametrize("declaration_text", ["{", "{}"])
def test_create_app_rejects_invalid_domain_declaration(
    isolated_domain_artifact: tuple[Path, Path], declaration_text: str
) -> None:
    """③ JSON 不正と必須項目欠落をアプリ生成前に拒否する。"""
    _, declaration = isolated_domain_artifact
    declaration.write_text(declaration_text, encoding="utf-8")

    with pytest.raises(DomainRuntimeError) as caught:
        api_app.create_app()

    assert caught.value.code == "INVALID_DECLARATION"


def test_create_app_accepts_valid_domain_artifact_without_node(
    isolated_domain_artifact: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """④ 正しい artifact なら Node を起動せずにアプリを生成する。"""
    assert all(path.is_file() for path in isolated_domain_artifact)

    def reject_node_start(_host: domainrt_host.NodeDomainHost) -> None:
        """Node の起動を試みた場合に試験を失敗させる。"""
        pytest.fail("create_app は Node を起動しない")

    monkeypatch.setattr(domainrt_host.NodeDomainHost, "_start", reject_node_start)
    app = api_app.create_app()

    assert app.title == "Pitchlog API"


def test_preparing_read_metadata_keeps_two_real_c2_routes() -> None:
    """論理read1行に対応する実GET2件とC2操作IDの固定登録を照合する。"""
    from pitchlog.api.tenant_access import _MATCH_OPERATIONS, TenantMatchedRoute

    routes = [
        route
        for router in api_app.ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute)
        and route.path in {"/games", "/games/{game_id}"}
        and route.methods == {"GET"}
    ]
    assert len(routes) == 2
    assert {
        (route.path, tuple(sorted(route.methods or ())), route.operation_id)
        for route in routes
    } == {
        ("/games", ("GET",), "preparing_game_list"),
        ("/games/{game_id}", ("GET",), "preparing_game_detail"),
    }
    assert all(isinstance(route, TenantMatchedRoute) for route in routes)
    assert {"preparing_game_list", "preparing_game_detail"} <= _MATCH_OPERATIONS


@pytest.mark.anyio
async def test_missing_rg1_configuration_keeps_health_read_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """書込制御未配置を、正常readの起動失敗や自動openへ広げない。"""
    from pitchlog.recording_rights import rg1_lifecycle

    monkeypatch.setattr(api_app, "_RG1_CLIENT_CONFIG_PATH", tmp_path / "missing.json")
    app = api_app.create_app()
    assert rg1_lifecycle._runtime_client is None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200


def test_untrusted_rg1_configuration_does_not_enable_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """非root配置を読取値の一致だけで制御clientへ採用しない。"""
    from pitchlog.recording_rights import rg1_lifecycle

    config = tmp_path / "untrusted.json"
    config.write_text("{}")
    monkeypatch.setattr(api_app, "_RG1_CLIENT_CONFIG_PATH", config)
    with pytest.raises(rg1_lifecycle.RG1ControlUnavailable):
        api_app.create_app()
    assert rg1_lifecycle._runtime_client is None
