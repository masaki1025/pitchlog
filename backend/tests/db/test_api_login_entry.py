"""ログイン入口の実 DB 直叩きと失敗経路の時間的一様性を検査する。"""

from __future__ import annotations

import asyncio
import base64
import secrets
from statistics import median
from threading import Lock
from time import perf_counter
from uuid import uuid4

import psycopg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL

from pitchlog.api.app import create_app
from pitchlog.api.routers import auth

from .conftest import ProvisionedProductCatalog
from .test_product_authz_authn_app import (
    _SETTINGS,
    _TEAM_LOGIN_SETTING_KEYS,
    _app_dsn,
    _counter,
    _seed_identity,
    _seed_settings,
    _setting,
)

pytestmark = pytest.mark.requires_db


def _login_engine(app_dsn: str) -> Engine:
    """実アプリロールの HTTP 試験用接続資源を作る。"""
    connection_options = conninfo_to_dict(app_dsn)
    return create_engine(
        URL.create(
            "postgresql+psycopg",
            username=str(connection_options["user"]),
            password=str(connection_options["password"]),
            host=str(connection_options["host"]),
            port=int(str(connection_options["port"])),
            database=str(connection_options["dbname"]),
        ),
        connect_args={"sslmode": "disable", "gssencmode": "disable"},
    )


def _login_app(monkeypatch: pytest.MonkeyPatch, engine: Engine) -> FastAPI:
    """試験用署名鍵と実 DB 接続を使うアプリを作る。"""
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )
    app = create_app()
    monkeypatch.setattr(auth, "get_login_connection", lambda: engine)
    return app


@pytest.mark.anyio
async def test_login_entry_reaches_database_and_keeps_failures_uniform(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ASGI の製品入口から実 DB を通し、発行先と失敗応答を確かめる。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    identity = _seed_identity(catalog, app_dsn)
    other = _seed_identity(catalog, app_dsn)
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )
    app = create_app()
    engine = _login_engine(app_dsn)
    monkeypatch.setattr(auth, "get_login_connection", lambda: engine)
    try:
        transport = ASGITransport(app=app, client=("192.0.2.45", 50123))
        async with AsyncClient(transport=transport, base_url="https://test") as client:
            wrong = secrets.token_urlsafe(24)
            known = await client.post(
                "/auth/login", json={"team_name": identity.name, "password": wrong}
            )
            missing = await client.post(
                "/auth/login",
                json={"team_name": f"missing{uuid4().hex[:12]}", "password": wrong},
            )
            success = await client.post(
                "/auth/login",
                json={"team_name": identity.name, "password": identity.password},
            )

        assert success.status_code == 200
        assert success.json() == {"status": "authenticated"}
        token_id = app.state.token_presentation.decode(
            success.cookies["__Host-pitchlog_token"]
        )
        with catalog.observer.cursor() as cursor:
            cursor.execute("SELECT id, tenant_id FROM public.tenant_tokens ORDER BY id")
            rows = cursor.fetchall()
        catalog.observer.rollback()
        assert rows == [(token_id, identity.tenant_id)]
        assert rows != [(token_id, other.tenant_id)]
        assert known.status_code == missing.status_code == 401
        assert known.content == missing.content
        assert "set-cookie" not in known.headers
        assert "set-cookie" not in missing.headers
    finally:
        engine.dispose()


@pytest.mark.anyio
async def test_nul_password_fails_and_is_counted_over_http(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NUL を含む入力も 401 として計数し、除去後の正答にはしない。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    engine = _login_engine(identity.app_dsn)
    app = _login_app(monkeypatch, engine)
    transport = ASGITransport(app=app, client=("192.0.2.45", 50123))
    try:
        async with AsyncClient(transport=transport, base_url="https://test") as client:
            nul = await client.post(
                "/auth/login",
                json={
                    "team_name": identity.name,
                    "password": identity.password[:2] + "\x00" + identity.password[2:],
                },
            )
            missing = await client.post(
                "/auth/login",
                json={"team_name": f"missing{uuid4().hex[:12]}", "password": "a\x00b"},
            )
            wrong = await client.post(
                "/auth/login",
                json={"team_name": identity.name, "password": "wrong"},
            )
            correct = await client.post(
                "/auth/login",
                json={"team_name": identity.name, "password": identity.password},
            )

        assert nul.status_code == missing.status_code == wrong.status_code == 401
        assert nul.content == missing.content == wrong.content
        assert all("set-cookie" not in item.headers for item in (nul, missing, wrong))
        assert correct.status_code == 200
        assert [row[1] for row in _counter(catalog, "src:192.0.2.45")] == [3]
    finally:
        engine.dispose()


@pytest.mark.anyio
async def test_missing_or_invalid_login_settings_reject_http_without_cookie(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4 設定値それぞれの欠落・不正を HTTP で拒否し Cookie を出さない。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    engine = _login_engine(identity.app_dsn)
    app = _login_app(monkeypatch, engine)
    transport = ASGITransport(app=app, client=("192.0.2.45", 50123))
    try:
        async with AsyncClient(transport=transport, base_url="https://test") as client:
            for key in _TEAM_LOGIN_SETTING_KEYS:
                for bad in (None, "invalid"):
                    if bad is None:
                        with catalog.applicator.cursor() as cursor:
                            cursor.execute(
                                "DELETE FROM public.system_settings WHERE key = %s",
                                (key,),
                            )
                        catalog.applicator.commit()
                    else:
                        _setting(catalog, key, bad)
                    response = await client.post(
                        "/auth/login",
                        json={
                            "team_name": identity.name,
                            "password": identity.password,
                        },
                    )
                    assert response.status_code == 401
                    assert "set-cookie" not in response.headers
                    _setting(catalog, key, _SETTINGS[key])
    finally:
        engine.dispose()


@pytest.mark.anyio
async def test_parallel_http_failures_use_multiple_connections_and_count_all(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """実 HTTP の並行失敗が複数接続を使い、全件計数される。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    engine = _login_engine(identity.app_dsn)
    app = _login_app(monkeypatch, engine)
    lock = Lock()
    active = 0
    peak = 0

    def checkout(_connection: object, _record: object, _proxy: object) -> None:
        """同時に使用中の DB 接続数を観測する。"""
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)

    def checkin(_connection: object, _record: object) -> None:
        """返却された DB 接続を観測する。"""
        nonlocal active
        with lock:
            active -= 1

    event.listen(engine, "checkout", checkout)
    event.listen(engine, "checkin", checkin)
    transport = ASGITransport(app=app, client=("192.0.2.45", 50123))
    attempts = 8
    try:
        async with AsyncClient(transport=transport, base_url="https://test") as client:
            responses = await asyncio.gather(
                *(
                    client.post(
                        "/auth/login",
                        json={"team_name": identity.name, "password": "wrong"},
                    )
                    for _ in range(attempts)
                )
            )

        assert peak >= 2
        assert active == 0
        assert all(response.status_code == 401 for response in responses)
        assert all("set-cookie" not in response.headers for response in responses)
        assert sum(row[1] for row in _counter(catalog, "src:192.0.2.45")) == attempts
    finally:
        engine.dispose()


def test_failed_login_known_missing_medians_stay_within_first_delay_step(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """名前の有無ごとに 30 回測り、実行時間の中央値を設定値と比べる。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    identity = _seed_identity(catalog, app_dsn)
    missing_name = f"missing{uuid4().hex[:12]}"
    wrong = secrets.token_urlsafe(24)
    samples: dict[str, list[float]] = {"known": [], "missing": []}

    # 毎回別の試行元にして各カウンタを初回失敗に保ち、予約票の待ちを計測に混ぜない。
    # 両群を交互に測り、DB の経時的な負荷変動も片方へ偏らせない。
    with psycopg.connect(app_dsn) as connection, connection.cursor() as cursor:
        for _ in range(30):
            for kind, name in (("known", identity.name), ("missing", missing_name)):
                source = f"timing-{uuid4().hex}"
                started = perf_counter()
                cursor.execute(
                    "SELECT token_id, wait_ms FROM authn.login_attempt(%s, %s, %s)",
                    (name, wrong, source),
                )
                row = cursor.fetchone()
                elapsed_ms = (perf_counter() - started) * 1000
                connection.commit()
                assert row == (None, 0)
                samples[kind].append(elapsed_ms)

    assert len(samples["known"]) == len(samples["missing"]) == 30
    first_delay_step_ms = _SETTINGS["auth.team_login.throttle_step_ms"]
    assert abs(median(samples["known"]) - median(samples["missing"])) < (
        first_delay_step_ms
    )


@pytest.mark.anyio
async def test_login_entry_does_not_bind_another_tenants_password_to_named_team(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """単一チーム名へのログインで別テナントの PW を受け付けない。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    first = _seed_identity(catalog, app_dsn)
    second = _seed_identity(catalog, app_dsn)
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )
    app = create_app()
    engine = _login_engine(app_dsn)
    monkeypatch.setattr(auth, "get_login_connection", lambda: engine)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://test"
        ) as client:
            crossed = await client.post(
                "/auth/login",
                json={"team_name": first.name, "password": second.password},
            )
            own = await client.post(
                "/auth/login",
                json={"team_name": second.name, "password": second.password},
            )

        assert crossed.status_code == 401
        assert "set-cookie" not in crossed.headers
        assert own.status_code == 200
        token_id = app.state.token_presentation.decode(
            own.cookies["__Host-pitchlog_token"]
        )
        with catalog.observer.cursor() as cursor:
            cursor.execute(
                "SELECT tenant_id FROM public.tenant_tokens WHERE id = %s", (token_id,)
            )
            row = cursor.fetchone()
        catalog.observer.rollback()
        assert row == (second.tenant_id,)
        assert row != (first.tenant_id,)
    finally:
        engine.dispose()
