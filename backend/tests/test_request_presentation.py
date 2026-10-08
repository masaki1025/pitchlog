"""要求からの提示値の取り出しと CSRF 条件を検証する。"""

import ast
import inspect
import logging
from importlib.util import resolve_name
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient

from pitchlog.api import request_presentation
from pitchlog.api.app import create_app
from pitchlog.api.request_presentation import RequestGateError, require_presented_token

_COOKIE_NAME = "__Host-pitchlog_token"
_ALLOWED_ORIGIN = "https://allowed.example"
_METHODS = ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE", "PROPFIND"]


def _make_test_app(received: list[str]) -> FastAPI:
    """依存関数だけを仮の入口へ結線した検証用アプリを作る。"""
    app = create_app()

    @app.api_route("/probe", methods=_METHODS)
    async def probe(
        token: Annotated[str, Depends(require_presented_token)],
    ) -> dict[str, bool]:
        """提示値を応答へ出さずに依存関数の戻り値を記録する。"""
        received.append(token)
        return {"accepted": True}

    return app


@pytest.mark.anyio
@pytest.mark.parametrize("cookie", [None, ""], ids=["missing", "empty"])
async def test_missing_or_empty_cookie_returns_fixed_401(cookie: str | None) -> None:
    """Cookie の欠落と空値を同じ 401 封筒で拒否する。"""
    received: list[str] = []
    transport = ASGITransport(app=_make_test_app(received), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        if cookie is not None:
            client.cookies.set(_COOKIE_NAME, cookie)
        response = await client.get("/probe")

    assert response.status_code == 401
    assert response.json() == {"error": {"message": "認証情報がありません"}}
    assert received == []


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
async def test_safe_methods_skip_csrf_checks(
    method: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """安全なメソッドは CSRF 用ヘッダと許可値の設定なしで通す。"""
    monkeypatch.delenv("PITCHLOG_ALLOWED_ORIGINS", raising=False)
    received: list[str] = []
    transport = ASGITransport(app=_make_test_app(received))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(_COOKIE_NAME, "opaque.value")
        response = await client.request(method, "/probe")

    assert response.status_code == 200
    assert received == ["opaque.value"]


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "PROPFIND"])
async def test_state_changing_and_unknown_methods_require_csrf(
    method: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """状態変更と未知のメソッドを CSRF 検査の対象にする。"""
    monkeypatch.setenv("PITCHLOG_ALLOWED_ORIGINS", _ALLOWED_ORIGIN)
    received: list[str] = []
    transport = ASGITransport(app=_make_test_app(received))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(_COOKIE_NAME, "opaque.value")
        response = await client.request(method, "/probe")

    assert response.status_code == 403
    assert response.json() == {"error": {"message": "要求を確認できません"}}
    assert received == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("allowed", "headers"),
    [
        (_ALLOWED_ORIGIN, {"Origin": _ALLOWED_ORIGIN}),
        (_ALLOWED_ORIGIN, {"X-Pitchlog-Request": "0", "Origin": _ALLOWED_ORIGIN}),
        (_ALLOWED_ORIGIN, {"X-Pitchlog-Request": "1"}),
        (
            _ALLOWED_ORIGIN,
            {"X-Pitchlog-Request": "1", "Origin": "https://other.example"},
        ),
        ("", {"X-Pitchlog-Request": "1", "Origin": _ALLOWED_ORIGIN}),
        ("  ,  ", {"X-Pitchlog-Request": "1", "Origin": _ALLOWED_ORIGIN}),
        ("*", {"X-Pitchlog-Request": "1", "Origin": _ALLOWED_ORIGIN}),
    ],
    ids=[
        "missing-custom-header",
        "wrong-custom-header",
        "missing-origin",
        "wrong-origin",
        "empty-configuration",
        "blank-configuration",
        "wildcard-configuration",
    ],
)
async def test_csrf_rejections_return_fixed_403(
    allowed: str, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """CSRF の各欠落と不一致を同じ固定封筒で拒否する。"""
    monkeypatch.setenv("PITCHLOG_ALLOWED_ORIGINS", allowed)
    received: list[str] = []
    transport = ASGITransport(app=_make_test_app(received))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(_COOKIE_NAME, "opaque.value")
        response = await client.post("/probe", headers=headers)

    assert response.status_code == 403
    assert response.json() == {"error": {"message": "要求を確認できません"}}
    assert received == []


@pytest.mark.anyio
async def test_unset_allowed_origins_rejects_state_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """許可値の環境変数が未設定なら状態変更を拒否する。"""
    monkeypatch.delenv("PITCHLOG_ALLOWED_ORIGINS", raising=False)
    received: list[str] = []
    transport = ASGITransport(app=_make_test_app(received))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(_COOKIE_NAME, "opaque.value")
        response = await client.post(
            "/probe",
            headers={"X-Pitchlog-Request": "1", "Origin": _ALLOWED_ORIGIN},
        )

    assert response.status_code == 403
    assert received == []


@pytest.mark.anyio
@pytest.mark.parametrize("origin", [_ALLOWED_ORIGIN, "http://allowed.example:8080"])
async def test_valid_state_change_returns_opaque_token_to_dependency_only(
    origin: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """正しい要求の提示値を加工せず返し、応答には載せない。"""
    monkeypatch.setenv(
        "PITCHLOG_ALLOWED_ORIGINS", f" https://other.example , {origin} "
    )
    token = "opaque.part.with.dots"
    received: list[str] = []
    transport = ASGITransport(app=_make_test_app(received))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(_COOKIE_NAME, token)
        response = await client.post(
            "/probe",
            headers={"X-Pitchlog-Request": "1", "Origin": origin},
        )

    assert response.status_code == 200
    assert response.json() == {"accepted": True}
    assert received == [token]
    assert token not in response.text


@pytest.mark.anyio
async def test_rejection_never_exposes_token_or_origin(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """拒否時の応答・例外・ログに提示値や Origin の値を出さない。"""
    token = "private-token-opaque"
    origin = "https://private-origin.example"
    monkeypatch.setenv("PITCHLOG_ALLOWED_ORIGINS", _ALLOWED_ORIGIN)
    caplog.set_level(logging.DEBUG)
    received: list[str] = []
    transport = ASGITransport(app=_make_test_app(received), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(_COOKIE_NAME, token)
        response = await client.post(
            "/probe", headers={"X-Pitchlog-Request": "1", "Origin": origin}
        )

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [
                (b"cookie", f"{_COOKIE_NAME}={token}".encode()),
                (b"x-pitchlog-request", b"1"),
                (b"origin", origin.encode()),
            ],
        }
    )
    with pytest.raises(RequestGateError) as caught:
        await require_presented_token(request)

    assert response.status_code == 403
    assert response.json() == {"error": {"message": "要求を確認できません"}}
    assert caught.value.reason == "csrf"
    for value in (token, origin):
        assert value not in response.text
        assert value not in str(caught.value)
        assert value not in repr(caught.value)
        assert value not in caplog.text
    assert received == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalid_origin",
    [
        "null",
        "*",
        "https://*.example",
        "allowed.example",
        "//allowed.example",
        "ftp://allowed.example",
        "https://",
        "https://allowed.example/",
        "https://allowed.example/path",
        "https://allowed.example?query=1",
        "https://allowed.example#fragment",
        "https://user@allowed.example",
        "https://allowed.example:invalid",
    ],
)
async def test_invalid_origin_entries_cannot_authorize_matching_requests(
    invalid_origin: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """不正な設定要素と一致する Origin を許可しない。"""
    monkeypatch.setenv(
        "PITCHLOG_ALLOWED_ORIGINS", f"{_ALLOWED_ORIGIN}, {invalid_origin}"
    )
    received: list[str] = []
    transport = ASGITransport(app=_make_test_app(received))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(_COOKIE_NAME, "opaque.value")
        response = await client.post(
            "/probe",
            headers={"X-Pitchlog-Request": "1", "Origin": invalid_origin},
        )

    assert response.status_code == 403
    assert response.json() == {"error": {"message": "要求を確認できません"}}
    assert received == []


@pytest.mark.anyio
async def test_valid_origin_survives_invalid_configuration_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不正な要素を除外しても正しい許可値は使える。"""
    monkeypatch.setenv(
        "PITCHLOG_ALLOWED_ORIGINS",
        f"null, https://allowed.example/, *, {_ALLOWED_ORIGIN}",
    )
    received: list[str] = []
    transport = ASGITransport(app=_make_test_app(received))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(_COOKIE_NAME, "opaque.value")
        response = await client.post(
            "/probe",
            headers={"X-Pitchlog-Request": "1", "Origin": _ALLOWED_ORIGIN},
        )

    assert response.status_code == 200
    assert received == ["opaque.value"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("configured", "serialized"),
    [
        ("HTTPS://App.Example", "https://app.example"),
        ("https://app.example:443", "https://app.example"),
        ("HTTP://App.Example:80", "http://app.example"),
        ("http://app.example:8080", "http://app.example:8080"),
        ("https://[2001:DB8::1]:443", "https://[2001:db8::1]"),
        ("HTTPS://[2001:DB8::1]:8443", "https://[2001:db8::1]:8443"),
        (
            "https://[2001:0DB8:0000:0000:0000:0000:0000:0001]",
            "https://[2001:db8::1]",
        ),
        ("https://xn--bcher-kva.example", "https://xn--bcher-kva.example"),
        ("http://192.0.2.1:80", "http://192.0.2.1"),
    ],
)
async def test_configured_origin_is_serialized_before_matching(
    configured: str, serialized: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """設定値をシリアライズし、非既定ポートと IPv6 の括弧を保つ。"""
    monkeypatch.setenv("PITCHLOG_ALLOWED_ORIGINS", configured)
    received: list[str] = []
    transport = ASGITransport(app=_make_test_app(received))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(_COOKIE_NAME, "opaque.value")
        response = await client.post(
            "/probe",
            headers={"X-Pitchlog-Request": "1", "Origin": serialized},
        )

    assert response.status_code == 200
    assert received == ["opaque.value"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("configured", "request_origin"),
    [
        ("HTTPS://App.Example", "HTTPS://App.Example"),
        ("https://app.example:443", "https://app.example:443"),
        ("HTTP://App.Example:80", "HTTP://App.Example:80"),
        ("https://[2001:DB8::1]:443", "https://[2001:DB8::1]:443"),
    ],
)
async def test_nonserialized_request_origin_is_rejected(
    configured: str, request_origin: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """要求の Origin は正規化せずに完全一致で判定する。"""
    monkeypatch.setenv("PITCHLOG_ALLOWED_ORIGINS", configured)
    received: list[str] = []
    transport = ASGITransport(app=_make_test_app(received))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(_COOKIE_NAME, "opaque.value")
        response = await client.post(
            "/probe",
            headers={"X-Pitchlog-Request": "1", "Origin": request_origin},
        )

    assert response.status_code == 403
    assert response.json() == {"error": {"message": "要求を確認できません"}}
    assert received == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalid_configuration",
    ["https://[::1", "https://app.example:70000", "https://app.example:invalid"],
)
async def test_unserializable_configuration_fails_closed(
    invalid_configuration: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """解析時に失敗する設定値から 500 を出さず、許可もしない。"""
    monkeypatch.setenv("PITCHLOG_ALLOWED_ORIGINS", invalid_configuration)
    received: list[str] = []
    transport = ASGITransport(app=_make_test_app(received), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(_COOKIE_NAME, "opaque.value")
        response = await client.post(
            "/probe",
            headers={"X-Pitchlog-Request": "1", "Origin": "https://app.example"},
        )

    assert response.status_code == 403
    assert response.json() == {"error": {"message": "要求を確認できません"}}
    assert received == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalid_origin",
    [
        "https://[v1.foo]",
        "https://[fe80::1%25eth0]",
        "https://app.example.",
        "https://bücher.example",
        f"https://{'a' * 64}.example",
        f"https://{'.'.join(['a' * 63] * 4)}",
        "https://app.example:0",
        "https://app.example:65536",
        "https://app.example:0443",
        "https://app_host.example",
    ],
    ids=[
        "ipvfuture",
        "ipv6-zone-id",
        "trailing-dot",
        "non-ascii-host",
        "long-label",
        "long-host",
        "port-zero",
        "port-too-large",
        "port-leading-zero",
        "underscore-host",
    ],
)
async def test_closed_origin_grammar_rejects_invalid_entries(
    invalid_origin: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """閉じた文法の外にある値は許可集合へ入れない。"""
    monkeypatch.setenv("PITCHLOG_ALLOWED_ORIGINS", invalid_origin)
    received: list[str] = []
    transport = ASGITransport(app=_make_test_app(received), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(_COOKIE_NAME, "opaque.value")
        response = await client.post(
            "/probe",
            headers={
                b"X-Pitchlog-Request": b"1",
                b"Origin": invalid_origin.encode("latin1"),
            },
        )

    assert request_presentation._serialize_allowed_origin(invalid_origin) is None
    assert response.status_code == 403
    assert response.json() == {"error": {"message": "要求を確認できません"}}
    assert received == []


@pytest.mark.anyio
async def test_ipvfuture_cannot_authorize_dns_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IPvFuture の括弧を外した DNS 名にも権限を与えない。"""
    monkeypatch.setenv("PITCHLOG_ALLOWED_ORIGINS", "https://[v1.foo]")
    received: list[str] = []
    transport = ASGITransport(app=_make_test_app(received))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(_COOKIE_NAME, "opaque.value")
        response = await client.post(
            "/probe",
            headers={"X-Pitchlog-Request": "1", "Origin": "https://v1.foo"},
        )

    assert response.status_code == 403
    assert response.json() == {"error": {"message": "要求を確認できません"}}
    assert received == []


def _assert_no_identity_verification_imports(source: str) -> None:
    """相対参照の解決後に禁止 import と動的 import を拒否する。"""
    tree = ast.parse(source)
    package = request_presentation.__package__
    assert package is not None
    blocked_modules = ("pitchlog.authn", "pitchlog.authz", "pitchlog.repositories")
    blocked_names = {
        "authn",
        "authz",
        "repositories",
        "TenantContext",
        "verify_token",
        "verify_tenant_id",
    }
    dynamic_import_names = {"__import__", "import_module"}

    def is_blocked(module: str) -> bool:
        """禁止されたモジュールとその子を判別する。"""
        return any(
            module == blocked or module.startswith(f"{blocked}.")
            for blocked in blocked_modules
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(not is_blocked(alias.name) for alias in node.names)
            assert all(alias.name not in blocked_names for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = resolve_name(f"{'.' * node.level}{module}", package)
            assert not is_blocked(module)
            assert all(alias.name not in blocked_names for alias in node.names)
            assert all(not is_blocked(f"{module}.{alias.name}") for alias in node.names)
            if module in {"importlib", "builtins"}:
                dynamic_import_names.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name in {"import_module", "__import__"}
                )

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in dynamic_import_names
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"import_module", "__import__"}


def test_dependency_module_has_no_identity_verification_imports() -> None:
    """要求面が本人確認・テナント文脈を import しない。"""
    _assert_no_identity_verification_imports(inspect.getsource(request_presentation))


@pytest.mark.parametrize(
    "source",
    [
        "from .. import authn",
        "from ..authn import verify_tenant_id",
        "from . import TenantContext",
        'import importlib\nimportlib.import_module("pitchlog.authn")',
        '__import__("pitchlog.authn")',
        'from importlib import import_module as load\nload("pitchlog.authn")',
    ],
    ids=[
        "relative-package-import",
        "relative-module-import",
        "relative-name-import",
        "importlib-call",
        "built-in-import-call",
        "aliased-importlib-call",
    ],
)
def test_identity_import_guard_rejects_synthetic_bypasses(source: str) -> None:
    """相対・動的 import の合成変異を同じ検査関数が拒否する。"""
    with pytest.raises(AssertionError):
        _assert_no_identity_verification_imports(source)
