"""C2照合metadataと業務境界の優先順位を実HTTPで検証する。"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from test_roster_boundary import (
    _ORIGIN,
    _PLAYER_A,
    _TEAM_A,
    _TENANT_A,
    _TENANT_B,
    _client_app,
    _PlayerStore,
    _team_client_app,
    _TeamStore,
)

from pitchlog.api.routers import players, team_records
from pitchlog.repositories.context import TenantContext

_EXPECTED = "X-Pitchlog-Expected-Tenant"
_CHALLENGE = "X-Pitchlog-Tenant-Challenge"
_ACK = "X-Pitchlog-Tenant-Match"
_CHALLENGE_VALUE = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
_ROUTES = (
    ("GET", "/team-records"),
    ("POST", "/team-records"),
    ("PATCH", f"/team-records/{_TEAM_A}"),
    ("GET", "/players"),
    ("POST", "/players"),
    ("GET", f"/players/{_PLAYER_A}"),
    ("PATCH", f"/players/{_PLAYER_A}"),
)


def _headers() -> list[tuple[str, str]]:
    """CSRFと照合metadataの正規入力を返す。"""
    return [
        ("Origin", _ORIGIN),
        ("X-Pitchlog-Request", "1"),
        (_EXPECTED, str(_TENANT_A)),
        (_CHALLENGE, _CHALLENGE_VALUE),
    ]


def _valid_body(method: str, path: str) -> dict[str, str] | None:
    """metadata正常時に成功する本文を成功・拒否の両試験で共有する。"""
    body = None if method == "GET" else {"name": "変更"}
    if method == "POST" and path == "/players":
        assert body is not None
        body.update(team_record_id=str(_TEAM_A), roster_status_key="active")
    return body


def _invalid_headers(field: str, fault: str) -> list[tuple[str, str]]:
    """一つのmetadataを欠落・重複・非canonicalなどへ破損する。"""
    headers = [(key, value) for key, value in _headers() if key != field]
    value = str(_TENANT_A) if field == _EXPECTED else _CHALLENGE_VALUE
    if fault == "missing":
        return headers
    if fault == "duplicate":
        return [*headers, (field, value), (field, value)]
    replacements = {
        "uppercase": value.upper(),
        "compact": value.replace("-", ""),
        "space": f" {value}",
        "invalid": "not-a-uuid",
        "comma": f"{value},{value}",
        "mismatch": str(_TENANT_B),
    }
    return [*headers, (field, replacements[fault])]


@pytest.mark.anyio
@pytest.mark.parametrize(("method", "path"), _ROUTES)
@pytest.mark.parametrize(
    ("field", "fault"),
    [
        (field, fault)
        for field in (_EXPECTED, _CHALLENGE)
        for fault in (
            "missing",
            "duplicate",
            "uppercase",
            "compact",
            "space",
            "invalid",
            "comma",
        )
    ]
    + [(_EXPECTED, "mismatch")],
)
@pytest.mark.parametrize("bad_input", ["none", "body", "json", "query"])
async def test_metadata_precedes_validation_and_transaction(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    method: str,
    path: str,
    field: str,
    fault: str,
    bad_input: str,
) -> None:
    """7経路で本文が正常でも不正でも固定404でtransactionを開始しない。"""
    caplog.set_level(logging.DEBUG)
    store = _PlayerStore()
    app = _client_app(monkeypatch, store)
    entered: list[TenantContext] = []

    @contextmanager
    def forbidden_scope(context: TenantContext) -> Iterator[object]:
        entered.append(context)
        raise AssertionError("照合拒否前にtransactionを開始した")
        yield

    monkeypatch.setattr(players, "tenant_transaction_scope", forbidden_scope)
    monkeypatch.setattr(team_records, "tenant_transaction_scope", forbidden_scope)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.request(
            method,
            path,
            headers=_invalid_headers(field, fault),
            json=_valid_body(method, path) if bad_input == "none" else None,
            content=(
                None
                if bad_input == "none"
                else "{"
                if bad_input == "json"
                else '{"name":null}'
            ),
            params={"limit": "invalid"} if bad_input == "query" else {"limit": "20"},
        )
    assert response.status_code == 404
    assert response.json() == {"error": {"message": "対象が見つかりません"}}
    assert entered == [] and store.operations == []
    assert response.headers["cache-control"] == "no-store"
    assert _ACK not in response.headers and _CHALLENGE not in response.headers
    assert str(_TENANT_A) not in response.text and str(_TENANT_B) not in response.text
    assert str(_TENANT_A) not in caplog.text and str(_TENANT_B) not in caplog.text
    assert _CHALLENGE_VALUE not in caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize(("method", "path"), _ROUTES)
async def test_all_seven_success_routes_return_match_evidence(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
) -> None:
    """実routerの成功2xxに固定ackと要求challengeを一度だけ付ける。"""
    app = (
        _team_client_app(monkeypatch, _TeamStore())
        if "team-records" in path
        else _client_app(monkeypatch, _PlayerStore())
    )
    body = _valid_body(method, path)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.request(
            method, path, json=body, headers=_headers(), params={"limit": 20}
        )
    assert 200 <= response.status_code < 300
    assert response.headers.get_list(_ACK) == ["1"]
    assert response.headers.get_list(_CHALLENGE) == [_CHALLENGE_VALUE]
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 404, 409, 422, 500])
async def test_failed_operation_never_returns_match_evidence(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    """照合後の失敗に偽の照合headerを残さずno-storeを維持する。"""
    app = _client_app(monkeypatch, _PlayerStore())

    def fail(*_: object) -> None:
        if status == 500:
            raise RuntimeError("意図した故障")
        raise HTTPException(
            status_code=status, headers={_ACK: "1", _CHALLENGE: _CHALLENGE_VALUE}
        )

    monkeypatch.setattr(players, "_run", fail)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="https://test",
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.get("/players?limit=20", headers=_headers())
    assert response.status_code == status
    assert _ACK not in response.headers and _CHALLENGE not in response.headers
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.anyio
@pytest.mark.parametrize(("method", "path"), _ROUTES)
async def test_authentication_precedes_missing_metadata(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
) -> None:
    """metadata欠落より先に認証の既存401を維持する。"""
    app = _client_app(monkeypatch, _PlayerStore())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        response = await client.request(method, path, content="{")
    assert response.status_code == 401
    assert _ACK not in response.headers and _CHALLENGE not in response.headers
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.anyio
async def test_foreign_and_nonexistent_expected_are_indistinguishable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """他tenantと不存在を応答内容で区別させない。"""
    app = _client_app(monkeypatch, _PlayerStore())
    responses = []
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        for tenant_id in (_TENANT_B, uuid4()):
            headers = [(key, value) for key, value in _headers() if key != _EXPECTED]
            responses.append(
                await client.get(
                    "/players", headers=[*headers, (_EXPECTED, str(tenant_id))]
                )
            )
    assert responses[0].status_code == responses[1].status_code == 404
    assert responses[0].content == responses[1].content


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("GET", "/health", 200),
        ("GET", "/version", 200),
        ("GET", "/auth/session", 401),
        ("POST", "/auth/login", 422),
        ("POST", "/auth/logout", 401),
        ("POST", "/players/status-preview", 422),
        ("POST", "/players/status-apply", 422),
        ("DELETE", f"/team-records/{_TEAM_A}", 200),
    ],
)
async def test_metadata_not_required_outside_initial_seven_routes(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    status: int,
) -> None:
    """認証・公開・在籍・削除経路へ照合metadataを拡張しない。"""
    app = _team_client_app(monkeypatch, _TeamStore())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        if path.startswith(("/players", "/team-records")):
            client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.request(
            method,
            path,
            json={},
            headers={
                "Origin": _ORIGIN,
                "X-Pitchlog-Request": "1",
            },
        )
    assert response.status_code == status
    assert _ACK not in response.headers and _CHALLENGE not in response.headers


@pytest.mark.anyio
@pytest.mark.parametrize("authenticated", [False, True])
@pytest.mark.parametrize(
    ("path", "status"),
    [
        ("/team-records", 405),
        (f"/team-records/{_TEAM_A}", 405),
        ("/players", 405),
        (f"/players/{_PLAYER_A}", 405),
        (f"/players/{_PLAYER_A}/missing", 404),
    ],
)
async def test_unmatched_method_or_path_uses_standard_routing(
    monkeypatch: pytest.MonkeyPatch,
    authenticated: bool,
    path: str,
    status: int,
) -> None:
    """対象外method/pathをmetadata照合やCookie更新へ巻き込まない。"""
    store = _PlayerStore()
    app = _client_app(monkeypatch, store)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        if authenticated:
            client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.put(path, content="{")
    assert response.status_code == status
    assert store.operations == []
    assert "set-cookie" not in response.headers
    assert _ACK not in response.headers and _CHALLENGE not in response.headers
