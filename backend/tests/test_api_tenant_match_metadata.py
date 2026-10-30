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


# client doubleによるHTTP輸送検査であり、実worker/DB開始の証拠ではない。
_START_GAME = uuid4()
_START_REQUEST = uuid4()
_START_DEVICE = uuid4()
_START_CREDENTIAL = "transport-only-device-credential"
_START_PROOF = "transport-only-right-proof"
_START_PATHS = (
    "/devices/enroll",
    f"/games/{_START_GAME}/start",
    f"/games/{_START_GAME}/start/resolve",
)


def _start_body():
    """既外形だけを持つ元要求を作り、名簿業務成功とは扱わない。"""
    side = [
        {
            "player_id": str(uuid4()),
            "batting_order": i,
            "fielding_position": {"kind": "fielding", "position": i},
        }
        for i in range(1, 10)
    ]
    return {
        "start_request_id": str(_START_REQUEST),
        "device_id": str(_START_DEVICE),
        "device_credential": _START_CREDENTIAL,
        "away": side,
        "home": side,
    }


def _start_http_app(monkeypatch, result):
    """既認証fixtureとclient輸送doubleだけを接合する。"""
    from pitchlog.api.routers import games

    calls = []

    class Client:
        def call(self, command):
            calls.append(command)
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(games, "_InitialBrokerClient", Client)
    return _client_app(monkeypatch, _PlayerStore()), calls


def _start_reply(path):
    """専用wire外形検査だけの資格付き応答を作る。"""
    from datetime import UTC, datetime

    from pydantic import SecretStr

    from pitchlog.api.schemas.game_start import (
        InitialDeviceEnrollmentResponse,
        InitialGameStartResponse,
    )
    from pitchlog.recording_rights.initial_grant_broker import _broker_d4, _BrokerReply

    if path == "/devices/enroll":
        return _BrokerReply(
            "enrolled",
            InitialDeviceEnrollmentResponse(
                tenant_id=_TENANT_A,
                device_id=_START_DEVICE,
                device_credential=SecretStr(_START_CREDENTIAL),
            ),
        )
    return _BrokerReply(
        "started",
        InitialGameStartResponse(
            tenant_id=_TENANT_A,
            game_id=_START_GAME,
            start_request_id=_START_REQUEST,
            device_id=_START_DEVICE,
            d4=_broker_d4(_TENANT_A, _START_GAME, 1),
            recovery_generation="1",
            recording_right_proof=SecretStr(_START_PROOF),
            started_at=datetime(2026, 10, 26, tzinfo=UTC),
            away_lineup_id=uuid4(),
            home_lineup_id=uuid4(),
        ),
    )


@pytest.mark.anyio
@pytest.mark.parametrize("path", _START_PATHS)
async def test_start_http_success_uses_original_cookie_and_dedicated_projection(
    monkeypatch,
    caplog,
    path,
):
    """実3POST/C2から同owner全値を送り、資格を専用成功fieldだけで返す。"""
    from pitchlog.recording_rights.initial_grant_broker import (
        _broker_command_source,
        _EnrollDeviceCommand,
        _ResolveStartCommand,
        _StartInitialGameCommand,
    )

    caplog.set_level(logging.DEBUG)
    reply = _start_reply(path)
    app, calls = _start_http_app(monkeypatch, reply)
    body = _start_body()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.post(
            path, headers=_headers(), json=None if path == "/devices/enroll" else body
        )
    assert response.status_code == 200
    assert len(calls) == 1
    selected = calls[0].original if type(calls[0]) is _ResolveStartCommand else calls[0]
    assert type(selected) is (
        _EnrollDeviceCommand if path == "/devices/enroll" else _StartInitialGameCommand
    )
    assert selected.identity.cookie.get_secret_value() == "token-a"
    assert selected.identity.expected_tenant_id == _TENANT_A
    assert str(selected.identity.challenge) == _CHALLENGE_VALUE
    wire = _broker_command_source(calls[0])
    assert not any("attempt" in key for key in wire)
    if path != "/devices/enroll":
        assert wire["request"] == body
        assert wire["game_id"] == str(_START_GAME)
    expected = reply.value.model_dump(mode="json")
    secret = (
        "device_credential" if path == "/devices/enroll" else "recording_right_proof"
    )
    expected[secret] = _START_CREDENTIAL if path == "/devices/enroll" else _START_PROOF
    assert response.json() == expected
    assert len(response.json()) == (3 if path == "/devices/enroll" else 10)
    assert response.headers["cache-control"] == "no-store"
    assert response.headers.get_list(_ACK) == ["1"]
    assert response.headers.get_list(_CHALLENGE) == [_CHALLENGE_VALUE]
    assert "token-a" not in response.text
    assert _START_CREDENTIAL not in caplog.text and _START_PROOF not in caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize("path", _START_PATHS)
@pytest.mark.parametrize(
    "field,fault",
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
async def test_start_http_c2_precedes_invalid_body_and_broker(
    monkeypatch, path, field, fault
):
    """3POSTで不正JSONより先にC2を拒否しworkerを呼ばない。"""
    app, calls = _start_http_app(monkeypatch, RuntimeError("呼出禁止"))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.post(
            path, headers=_invalid_headers(field, fault), content="{"
        )
    assert response.status_code == 404
    assert calls == []
    assert response.headers["cache-control"] == "no-store"
    assert _ACK not in response.headers and _CHALLENGE not in response.headers


@pytest.mark.anyio
@pytest.mark.parametrize("path", _START_PATHS)
@pytest.mark.parametrize(
    "fault,status",
    [
        ("no-cookie", 401),
        ("bad-cookie", 401),
        ("no-header", 403),
        ("bad-origin", 403),
        ("null-origin", 403),
    ],
)
async def test_start_http_auth_and_csrf_precede_body(monkeypatch, path, fault, status):
    """既Cookie/状態変更header/Origin拒否を本文より先に保つ。"""
    app, calls = _start_http_app(monkeypatch, RuntimeError("呼出禁止"))
    headers = _headers()
    if fault == "no-header":
        headers = [(k, v) for k, v in headers if k != "X-Pitchlog-Request"]
    if fault in ("bad-origin", "null-origin"):
        headers = [(k, v) for k, v in headers if k != "Origin"]
        headers.append(
            ("Origin", "null" if fault == "null-origin" else "https://other.invalid")
        )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        if fault != "no-cookie":
            client.cookies.set(
                "__Host-pitchlog_token",
                "broken" if fault == "bad-cookie" else "token-a",
            )
        response = await client.post(path, headers=headers, content="{")
    assert response.status_code == status
    assert calls == []
    assert response.headers["cache-control"] == "no-store"
    assert _ACK not in response.headers and _CHALLENGE not in response.headers


@pytest.mark.anyio
@pytest.mark.parametrize("path", _START_PATHS[1:])
@pytest.mark.parametrize(
    "fault", ("json", "extra", "credential", "role", "server-field")
)
async def test_start_http_invalid_body_keeps_secrets_out_of_response_and_log(
    monkeypatch,
    caplog,
    path,
    fault,
):
    """不正JSON/extra/閉role/資格欠落を固定422へ閉じる。"""
    caplog.set_level(logging.DEBUG)
    app, calls = _start_http_app(monkeypatch, RuntimeError("呼出禁止"))
    body = _start_body()
    if fault == "extra":
        body[_START_CREDENTIAL] = _START_PROOF
    elif fault == "credential":
        body["device_credential"] = ""
    elif fault == "role":
        body["away"][0]["fielding_position"] = {"kind": _START_CREDENTIAL}
    elif fault == "server-field":
        body["attempt_id"] = str(uuid4())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.post(
            path,
            headers=_headers(),
            **(
                {"content": '{"device_credential":"' + _START_CREDENTIAL}
                if fault == "json"
                else {"json": body}
            ),
        )
    assert response.status_code == 422
    assert calls == []
    assert response.headers["cache-control"] == "no-store"
    assert _ACK not in response.headers and _CHALLENGE not in response.headers
    for secret in ("token-a", _START_CREDENTIAL, _START_PROOF):
        assert secret not in response.text and secret not in caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize("path", _START_PATHS)
@pytest.mark.parametrize(
    "fault", ("denied", "unavailable", "timeout", "driver", "bad-owner")
)
async def test_start_http_non_success_never_retries_or_returns_qualification(
    monkeypatch,
    caplog,
    path,
    fault,
):
    """不明/原例外/偽ownerを非成功にし、自動retryと成功補完をしない。"""
    from pitchlog.recording_rights.initial_grant_broker import _BrokerReply

    caplog.set_level(logging.DEBUG)
    if fault in ("denied", "unavailable"):
        result = _BrokerReply(fault)
    elif fault == "timeout":
        result = TimeoutError(_START_CREDENTIAL)
    elif fault == "driver":
        result = RuntimeError("token-a " + _START_PROOF)
    else:
        result = _start_reply(path)
        object.__setattr__(result.value, "tenant_id", _TENANT_B)
    app, calls = _start_http_app(monkeypatch, result)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.post(
            path,
            headers=_headers(),
            json=None if path == "/devices/enroll" else _start_body(),
        )
    assert response.status_code == (404 if fault == "denied" else 503)
    assert len(calls) == 1
    assert response.headers["cache-control"] == "no-store"
    assert _ACK not in response.headers and _CHALLENGE not in response.headers
    for secret in ("token-a", _START_CREDENTIAL, _START_PROOF):
        assert secret not in response.text and secret not in caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize("path", _START_PATHS[1:])
@pytest.mark.parametrize("status,expected", [("conflict", 409), ("unresolved", 503)])
async def test_start_http_unknown_retains_original_request(
    monkeypatch, path, status, expected
):
    """元要求を変更せず非成功を返し、新attemptを生成しない。"""
    import copy

    from pitchlog.recording_rights.initial_grant_broker import (
        _broker_command_source,
        _BrokerReply,
    )

    app, calls = _start_http_app(monkeypatch, _BrokerReply(status))
    body = _start_body()
    original = copy.deepcopy(body)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.post(path, headers=_headers(), json=body)
    assert response.status_code == expected
    assert body == original and len(calls) == 1
    wire = _broker_command_source(calls[0])
    assert wire["request"] == original
    assert not any("attempt" in key for key in wire)
    assert response.headers["cache-control"] == "no-store"
    assert _ACK not in response.headers and _CHALLENGE not in response.headers


@pytest.mark.anyio
@pytest.mark.parametrize("path", _START_PATHS[1:])
@pytest.mark.parametrize("field", ("game_id", "start_request_id", "device_id", "d4"))
async def test_start_http_rejects_foreign_owner_or_invalid_reference(
    monkeypatch,
    path,
    field,
):
    """既専用wireのowner4field/参照検査をHTTP成功投影前にも維持する。"""
    result = _start_reply(path)
    object.__setattr__(result.value, field, "invalid" if field == "d4" else uuid4())
    app, calls = _start_http_app(monkeypatch, result)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.post(path, headers=_headers(), json=_start_body())
    assert response.status_code == 503 and len(calls) == 1
    assert _START_PROOF not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert _ACK not in response.headers and _CHALLENGE not in response.headers


@pytest.mark.anyio
@pytest.mark.parametrize("path", _START_PATHS)
@pytest.mark.parametrize("fault", ("constructor", "unknown-reply", "unexpected-500"))
async def test_start_http_failures_are_no_store_without_retry(
    monkeypatch,
    caplog,
    path,
    fault,
):
    """client生成故障/未知応答/予期外500にも保存禁止を付ける。"""
    from pitchlog.api.routers import games

    caplog.set_level(logging.DEBUG)
    app, calls = _start_http_app(monkeypatch, None)
    constructed = []
    if fault == "constructor":

        def fail():
            constructed.append(True)
            raise RuntimeError(_START_CREDENTIAL)

        monkeypatch.setattr(games, "_InitialBrokerClient", fail)
    elif fault == "unexpected-500":

        def fixed_failure(command):
            raise RuntimeError("固定のHTTP故障")

        monkeypatch.setattr(games, "_initial_response", fixed_failure)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="https://test",
    ) as client:
        client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.post(
            path,
            headers=_headers(),
            json=None if path == "/devices/enroll" else _start_body(),
        )
    assert response.status_code == (500 if fault == "unexpected-500" else 503)
    assert len(calls) == (1 if fault == "unknown-reply" else 0)
    assert len(constructed) == (1 if fault == "constructor" else 0)
    assert response.headers["cache-control"] == "no-store"
    assert _ACK not in response.headers and _CHALLENGE not in response.headers
    for secret in ("token-a", _START_CREDENTIAL, _START_PROOF):
        assert secret not in response.text and secret not in caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize("suffix", ("start", "start/resolve"))
@pytest.mark.parametrize(
    "fault,status", [("cookie", 401), ("tenant", 404), ("path", 422)]
)
async def test_start_http_authentication_precedes_invalid_game_path(
    monkeypatch,
    suffix,
    fault,
    status,
):
    """URL外形不正でも認証/C2を先に実行し、実workerへ到達しない。"""
    app, calls = _start_http_app(monkeypatch, RuntimeError("呼出禁止"))
    headers = (
        _headers() if fault != "tenant" else _invalid_headers(_EXPECTED, "mismatch")
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        if fault != "cookie":
            client.cookies.set("__Host-pitchlog_token", "token-a")
        response = await client.post(
            f"/games/not-a-uuid/{suffix}", headers=headers, json=_start_body()
        )
    assert response.status_code == status and calls == []
    assert response.headers["cache-control"] == "no-store"
    assert _ACK not in response.headers and _CHALLENGE not in response.headers
