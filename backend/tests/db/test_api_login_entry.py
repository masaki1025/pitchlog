"""ログイン入口の実 DB 直叩きと失敗経路の時間的一様性を検査する。"""

from __future__ import annotations

import base64
import secrets
from statistics import median
from time import perf_counter
from uuid import uuid4

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from pitchlog.api.app import create_app
from pitchlog.api.routers import auth

from .conftest import ProvisionedProductCatalog
from .test_product_authz_authn_app import (
    _SETTINGS,
    _app_dsn,
    _seed_identity,
    _seed_settings,
)

pytestmark = pytest.mark.requires_db


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
    connection_options = conninfo_to_dict(app_dsn)
    engine = create_engine(
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
    connection_options = conninfo_to_dict(app_dsn)
    engine = create_engine(
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
