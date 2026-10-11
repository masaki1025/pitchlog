"""ログイン HTTP 経路を DB なしの ASGI 要求で検証する。"""

import asyncio
import base64
import logging
import secrets
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError

from pitchlog.api.app import create_app
from pitchlog.api.routers import auth
from pitchlog.authz import team_login


@pytest.fixture(autouse=True)
def _configure_signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """各試験のアプリへ独立した署名鍵を与える。"""
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )


@pytest.mark.anyio
@pytest.mark.parametrize("ttl_seconds", (13, 137))
async def test_success_sets_cookie_without_exposing_presentation(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    ttl_seconds: int,
) -> None:
    """成功時に全 Cookie 属性を付け、提示値を本文・URL・ログへ出さない。"""
    app = create_app()
    value = app.state.token_presentation.encode(uuid4())
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    connector = object()
    received: list[tuple[str, str, str, object, object]] = []

    def issue(
        team_name: str,
        password: str,
        source: str,
        presentation: object,
        resource: object,
    ) -> tuple[str, datetime]:
        """正しい資格情報を受けた境界の結果を代行する。"""
        received.append((team_name, password, source, presentation, resource))
        return value, expires_at

    monkeypatch.setattr(auth, "login_attempt", issue)
    monkeypatch.setattr(auth, "get_login_connection", lambda: connector)
    caplog.set_level(logging.DEBUG)
    transport = ASGITransport(app=app, client=("192.0.2.12", 50123))
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        response = await client.post(
            "/auth/login",
            json={"team_name": "known-team", "password": "correct-secret"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "authenticated"}
    assert received == [
        (
            "known-team",
            "correct-secret",
            "192.0.2.12",
            app.state.token_presentation,
            connector,
        )
    ]
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"__Host-pitchlog_token={value};")
    assert "httponly" in cookie.lower()
    assert "secure" in cookie.lower()
    assert "samesite=strict" in cookie.lower()
    assert "path=/" in cookie.lower()
    assert "domain=" not in cookie.lower()
    assert "max-age=" in cookie.lower()
    max_age = int(
        next(
            part.split("=", 1)[1]
            for part in cookie.split("; ")
            if part.startswith("Max-Age=")
        )
    )
    assert ttl_seconds - 2 <= max_age <= ttl_seconds
    assert value not in response.text
    assert value not in str(response.request.url)
    assert value not in caplog.text
    assert "correct-secret" not in response.text
    assert "correct-secret" not in caplog.text


@pytest.mark.anyio
async def test_failure_is_identical_for_known_and_unknown_teams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """存在する名前と無い名前の失敗を同じ応答にする。"""
    app = create_app()
    connector = object()
    boundary_returned = False
    sleeps: list[float] = []

    def deny(
        _team_name: str,
        _password: str,
        _source: str,
        _presentation: object,
        _resource: object,
    ) -> int:
        """境界の呼び出し完了後に待ち時間だけ返す。"""
        nonlocal boundary_returned
        boundary_returned = True
        return 350

    async def consume(seconds: float) -> None:
        """境界が戻ってから待ちが消費されることを記録する。"""
        assert boundary_returned
        sleeps.append(seconds)

    monkeypatch.setattr(auth, "login_attempt", deny)
    monkeypatch.setattr(auth, "get_login_connection", lambda: connector)
    monkeypatch.setattr(auth, "anyio", SimpleNamespace(sleep=consume))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        known = await client.post(
            "/auth/login", json={"team_name": "known", "password": "wrong"}
        )
        missing = await client.post(
            "/auth/login", json={"team_name": "missing", "password": "wrong"}
        )

    assert known.status_code == missing.status_code == 401
    assert known.content == missing.content
    assert "set-cookie" not in known.headers
    assert "set-cookie" not in missing.headers
    assert sleeps == [0.35, 0.35]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("client_address", "expected_source"),
    (
        (None, "unknown"),
        (("2001:db8:abcd:1234::1", 50123), "2001:db8:abcd:1234::"),
        (("2001:db8:abcd:1234::beef", 50124), "2001:db8:abcd:1234::"),
    ),
)
async def test_login_entry_normalizes_source_when_missing_or_ipv6(
    monkeypatch: pytest.MonkeyPatch,
    client_address: tuple[str, int] | None,
    expected_source: str,
) -> None:
    """試行元が取れない場合と IPv6 の /64 を HTTP 入口で固定する。"""
    app = create_app()
    sources: list[str] = []

    def deny(
        _team_name: str,
        _password: str,
        source: str,
        _presentation: object,
        _resource: object,
    ) -> int:
        """境界へ渡った正規化後の試行元を記録する。"""
        sources.append(source)
        return 0

    monkeypatch.setattr(auth, "login_attempt", deny)
    monkeypatch.setattr(auth, "get_login_connection", object)

    async def inline_call(work: Callable[[], int]) -> int:
        """試行元の試験では境界処理をインラインで実行する。"""
        return work()

    monkeypatch.setattr(auth, "run_in_threadpool", inline_call)
    transport = ASGITransport(app=app, client=cast(tuple[str, int], client_address))
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        response = await client.post(
            "/auth/login", json={"team_name": "known", "password": "wrong"}
        )

    assert response.status_code == 401
    assert "set-cookie" not in response.headers
    assert sources == [expected_source]


@pytest.mark.anyio
async def test_max_age_is_zero_when_expiry_has_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """発行期限が過去なら Cookie の残り秒数を 0 にする。"""
    app = create_app()
    value = app.state.token_presentation.encode(uuid4())
    monkeypatch.setattr(
        auth,
        "login_attempt",
        lambda *_args: (value, datetime.now(UTC) - timedelta(seconds=1)),
    )
    monkeypatch.setattr(auth, "get_login_connection", object)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        response = await client.post(
            "/auth/login", json={"team_name": "known", "password": "correct"}
        )

    assert response.status_code == 200
    assert "Max-Age=0" in response.headers["set-cookie"]


@pytest.mark.anyio
async def test_slow_verification_does_not_block_other_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """照合中もイベントループがヘルスチェックを処理できる。"""
    app = create_app()
    started = threading.Event()
    release = threading.Event()

    def wait_for_release(*_args: object) -> int:
        """スレッド内で照合を模擬し、解除後に失敗する。"""
        started.set()
        assert release.wait(timeout=5)
        return 0

    monkeypatch.setattr(auth, "login_attempt", wait_for_release)
    monkeypatch.setattr(auth, "get_login_connection", object)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        login_task = asyncio.create_task(
            client.post("/auth/login", json={"team_name": "known", "password": "wrong"})
        )
        try:
            assert await asyncio.to_thread(started.wait, 5)
            health = await asyncio.wait_for(client.get("/health"), timeout=2)
            assert health.status_code == 200
        finally:
            release.set()
        failed = await login_task

    assert failed.status_code == 401


@pytest.mark.anyio
async def test_waiting_failures_do_not_delay_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """多数の失敗が待機中でも成功した要求を処理できる。"""
    app = create_app()
    signed = app.state.token_presentation.encode(uuid4())
    expires_at = datetime.now(UTC) + timedelta(minutes=1)
    waiting = 0
    working = False
    all_waiting = asyncio.Event()
    release = asyncio.Event()
    failure_count = 41

    def attempt(
        _team_name: str,
        password: str,
        _source: str,
        _presentation: object,
        _resource: object,
    ) -> tuple[str, datetime] | int:
        """成功と失敗を DB を使わずに分岐させる。"""
        if password == "correct":
            return signed, expires_at
        return 7_000

    async def complete_work(
        work: Callable[[], tuple[str, datetime] | int],
    ) -> tuple[str, datetime] | int:
        """境界の仕事だけを終えてから経路へ結果を戻す。"""
        nonlocal working
        working = True
        try:
            return work()
        finally:
            working = False

    async def wait_without_worker(_seconds: float) -> None:
        """失敗要求をタイマー上に留め、同時に成功要求を送る。"""
        nonlocal waiting
        assert not working
        waiting += 1
        if waiting == failure_count:
            all_waiting.set()
        await release.wait()

    monkeypatch.setattr(auth, "login_attempt", attempt)
    monkeypatch.setattr(auth, "get_login_connection", object)
    monkeypatch.setattr(auth, "run_in_threadpool", complete_work)
    monkeypatch.setattr(auth, "anyio", SimpleNamespace(sleep=wait_without_worker))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        failures = [
            asyncio.create_task(
                client.post(
                    "/auth/login",
                    json={"team_name": "known", "password": "wrong"},
                )
            )
            for _ in range(failure_count)
        ]
        try:
            await asyncio.wait_for(all_waiting.wait(), timeout=5)
            success = await asyncio.wait_for(
                client.post(
                    "/auth/login",
                    json={"team_name": "known", "password": "correct"},
                ),
                timeout=2,
            )
            assert success.status_code == 200
            assert "set-cookie" in success.headers
        finally:
            release.set()
            denied = await asyncio.gather(*failures)

    assert len(denied) == failure_count
    assert all(response.status_code == 401 for response in denied)


def test_boundary_commits_before_returning_signed_value() -> None:
    """発行行 ID を接続終了後に署名し、期限とともに返す。"""
    presentation = create_app().state.token_presentation
    token_id = uuid4()
    expires_at = datetime.now(UTC) + timedelta(seconds=143)
    resource = MagicMock()
    connection = resource.begin.return_value.__enter__.return_value
    connection.execute.return_value.one.return_value = (token_id, 0, expires_at)

    result = team_login.login_attempt(
        "team", "private-password", "192.0.2.12", presentation, resource
    )

    assert isinstance(result, tuple)
    assert presentation.decode(result[0]) == token_id
    assert result[1] == expires_at
    resource.begin.return_value.__exit__.assert_called_once()
    statement, params = connection.execute.call_args.args
    assert str(statement) == (
        "SELECT token_id, wait_ms, expires_at "
        "FROM authn.login_attempt(:team_name, :password, :source)"
    )
    assert params == {
        "team_name": "team",
        "password": "private-password",
        "source": "192.0.2.12",
    }


def test_boundary_failure_returns_only_wait_time() -> None:
    """失敗時に提示値を作らず待ち時間だけ返す。"""
    presentation = create_app().state.token_presentation
    resource = MagicMock()
    connection = resource.begin.return_value.__enter__.return_value
    connection.execute.return_value.one.return_value = (None, 350, None)

    assert (
        team_login.login_attempt("team", "wrong", "192.0.2.12", presentation, resource)
        == 350
    )
    resource.begin.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize(
    ("team_name", "password"),
    (("team", "a\x00b"), ("te\x00am", "password")),
)
def test_boundary_counts_nul_input_through_impossible_name(
    team_name: str, password: str
) -> None:
    """NUL を DB に渡さず、成功不能な名前で失敗関数へ到達する。"""
    presentation = create_app().state.token_presentation
    resource = MagicMock()
    connection = resource.begin.return_value.__enter__.return_value
    connection.execute.return_value.one.return_value = (None, 0, None)

    assert (
        team_login.login_attempt(
            team_name, password, "192.0.2.12", presentation, resource
        )
        == 0
    )
    _statement, params = connection.execute.call_args.args
    assert params == {"team_name": None, "password": None, "source": "192.0.2.12"}


def test_boundary_rejects_other_signer_and_hides_database_error() -> None:
    """別の署名器と機密情報入りの接続例外を安全に拒否する。"""
    presentation = create_app().state.token_presentation
    other = type(presentation)(secrets.token_bytes(32))
    resource = MagicMock()
    with pytest.raises(TypeError, match="設定済みの署名器ではありません"):
        team_login.login_attempt("team", "password", "source", other, resource)
    resource.begin.assert_not_called()

    connection = resource.begin.return_value.__enter__.return_value
    connection.execute.side_effect = SQLAlchemyError("private-password")
    with pytest.raises(RuntimeError, match="ログインの照合を完了できない") as error:
        team_login.login_attempt(
            "team", "private-password", "source", presentation, resource
        )
    assert "private-password" not in str(error.value)
    assert error.value.__context__ is None
