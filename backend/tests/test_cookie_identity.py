"""通信断の認証継続に使う宣言とCookie送出制約を検証する。"""

import json
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

from pitchlog.api.app import ROUTERS
from pitchlog.api.cookie_identity import (
    _OPERATIONS,
    _load_policy,
    mark_same_token_cookie_route,
    same_token_cookie_headers,
)
from pitchlog.api.tenant_access import _MATCH_OPERATIONS


def test_declared_operations_are_exactly_tenant_matched_routes() -> None:
    """新しいC2 routeを宣言から取りこぼさない。"""
    assert set(_OPERATIONS) == _MATCH_OPERATIONS
    actual = {
        route.operation_id: (next(iter(route.methods)), route.path)
        for router in ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute)
        and route.methods is not None
        and route.operation_id in _MATCH_OPERATIONS
    }
    assert dict(_OPERATIONS) == actual


@pytest.mark.parametrize("status", [200, 201, 400, 404, 409, 422, 500, 503])
def test_matched_route_only_sends_verified_same_token_cookie(status: int) -> None:
    """handlerの別値/削除Cookieを転送せず真正認証の期限延長だけを送る。"""
    scope = {"type": "http", "state": {"renewed_cookie": "verified-same-token"}}
    mark_same_token_cookie_route(scope, "preparing_game_list", "GET", "/games")
    headers = [
        (b"content-type", b"application/json"),
        (b"Set-Cookie", b"other"),
        (b"set-cookie", b"deleted; Max-Age=0"),
    ]
    assert same_token_cookie_headers(scope, status, headers) == [
        (b"content-type", b"application/json"),
        (b"set-cookie", b"verified-same-token"),
    ]


def test_unauthorized_or_unverified_request_cannot_renew_cookie() -> None:
    """401又は真正認証の更新なしではhandlerがCookieを作れない。"""
    scope = {"type": "http", "state": {}}
    mark_same_token_cookie_route(scope, "preparing_game_list", "GET", "/games")
    assert same_token_cookie_headers(scope, 200, [(b"set-cookie", b"other")]) == []
    scope["state"]["renewed_cookie"] = "verified-same-token"
    assert same_token_cookie_headers(scope, 401, [(b"set-cookie", b"other")]) == []


@pytest.mark.parametrize("method,path", [("POST", "/games"), ("GET", "/gamesx")])
def test_marker_requires_exact_route(method: str, path: str) -> None:
    """自由なoperation名だけでは同値更新routeを名乗れない。"""
    scope = {"type": "http", "state": {"renewed_cookie": "same"}}
    mark_same_token_cookie_route(scope, "preparing_game_list", method, path)
    headers = [(b"set-cookie", b"original")]
    assert same_token_cookie_headers(scope, 200, headers) is headers


@pytest.mark.parametrize(
    "mutation", ["extra", "duplicate", "auth", "bool", "converter"]
)
def test_policy_rejects_invalid_declaration(tmp_path: Path, mutation: str) -> None:
    """未知形式を保護例外へ黙って採用しない。"""
    row = {"operationId": "example", "method": "GET", "path": "/games"}
    data = {
        "schemaVersion": 1,
        "semantics": "same-presented-token-renewal-only",
        "operations": [row],
    }
    if mutation == "extra":
        row["extra"] = "unused"
    elif mutation == "duplicate":
        data["operations"].append(dict(row))
    elif mutation == "auth":
        row["path"] = "/auth/session"
    elif mutation == "bool":
        data["schemaVersion"] = True
    else:
        row["path"] = "/games/{game_id:path}"
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        _load_policy(path)
