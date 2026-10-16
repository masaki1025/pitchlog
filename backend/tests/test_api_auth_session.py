"""認証session確認のHTTP契約をDBなしで検査する。"""

import base64
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from test_authz_tenant_context import make_tenant_context

from pitchlog.api.app import create_app
from pitchlog.api.routers import auth
from pitchlog.api.schemas.auth import AuthSessionResponse
from pitchlog.api.tenant_access import require_tenant_access
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.tokens import TenantOperationResult

_COOKIE = "__Host-pitchlog_token=presented"


@pytest.fixture(autouse=True)
def _configure_signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """APIアプリ生成に必要な試験用署名鍵を設定する。"""
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )


def _install_profile_result(
    monkeypatch: pytest.MonkeyPatch,
    result: TenantOperationResult,
) -> None:
    """固定operationの結果だけを返すトランザクション境界を設置する。"""

    @contextmanager
    def scope(_context: TenantContext) -> Iterator[object]:
        yield SimpleNamespace(run=lambda _operation: result)

    monkeypatch.setattr(auth, "tenant_transaction_scope", scope)


@pytest.mark.anyio
async def test_session_returns_only_verified_tenant_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """検証済み文脈と同じtenantのID・正規表示名だけを返す。"""
    tenant_id = uuid4()
    context = make_tenant_context(tenant_id)
    _install_profile_result(
        monkeypatch, TenantOperationResult(((tenant_id, "認可済みチーム"),))
    )
    app = create_app()
    app.dependency_overrides[require_tenant_access] = lambda: context

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        result = await client.get(
            "/auth/session?tenant_id=00000000-0000-0000-0000-000000000000",
            headers={"X-Tenant-ID": str(uuid4())},
        )

    assert result.status_code == 200
    assert result.json() == {
        "tenant_id": str(tenant_id),
        "team_name": "認可済みチーム",
    }
    assert "presented" not in result.text


@pytest.mark.anyio
async def test_session_requires_presented_cookie_before_profile_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cookieがなければtenant readを開始せず固定401を返す。"""

    def unexpected_scope(_context: TenantContext) -> object:
        raise AssertionError("未認証要求でtenant readを開始してはならない")

    monkeypatch.setattr(auth, "tenant_transaction_scope", unexpected_scope)
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        result = await client.get("/auth/session")

    assert result.status_code == 401
    assert result.json() == {"error": {"message": "認証情報がありません"}}


@pytest.mark.anyio
async def test_session_maps_missing_profile_to_uniform_unauthenticated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """検証後にtenant行がなければ存在理由を漏らさず401へ写す。"""
    context = make_tenant_context(uuid4())
    _install_profile_result(monkeypatch, TenantOperationResult(()))
    app = create_app()
    app.dependency_overrides[require_tenant_access] = lambda: context

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        result = await client.get("/auth/session", headers={"Cookie": _COOKIE})

    assert result.status_code == 401
    assert result.json() == {"error": {"message": "認証情報がありません"}}
    assert str(context.tenant_id) not in result.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "rows",
    [
        ((uuid4(), "別テナント"),),
        ((str(uuid4()), "文字列ID"),),
        ((UUID("00000000-0000-0000-0000-000000000001"), ""),),
        ((UUID("00000000-0000-0000-0000-000000000001"), 123),),
        ((uuid4(), "余分", "列"),),
        (
            (UUID("00000000-0000-0000-0000-000000000001"), "1行目"),
            (uuid4(), "2行目"),
        ),
    ],
)
async def test_session_rejects_unverified_result_shapes_without_leakage(
    monkeypatch: pytest.MonkeyPatch,
    rows: tuple[tuple[object, ...], ...],
) -> None:
    """相関・型・件数を確認できない結果を成功DTOにしない。"""
    context = make_tenant_context(UUID("00000000-0000-0000-0000-000000000001"))
    _install_profile_result(monkeypatch, TenantOperationResult(cast(Any, rows)))
    app = create_app()
    app.dependency_overrides[require_tenant_access] = lambda: context

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="https://test",
    ) as client:
        result = await client.get("/auth/session", headers={"Cookie": _COOKIE})

    assert result.status_code == 500
    assert result.json() == {"error": {"message": "サーバー内部でエラーが発生しました"}}
    assert "別テナント" not in result.text
    assert "文字列ID" not in result.text
    assert "1行目" not in result.text
    assert "2行目" not in result.text


def test_session_response_rejects_extra_fields() -> None:
    """応答DTOがtenant IDと表示名以外を受理しない。"""
    with pytest.raises(ValidationError):
        AuthSessionResponse.model_validate(
            {"tenant_id": str(uuid4()), "team_name": "チーム", "token": "secret"}
        )
