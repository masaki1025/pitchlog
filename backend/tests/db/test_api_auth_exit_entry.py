"""ログアウトと PW 変更の HTTP 入口を実 DB に通して検査する。"""

import base64
import json
import re
import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL

from pitchlog.api.app import create_app
from pitchlog.api.routers import auth
from pitchlog.authz.verified_tenant import verify_tenant_id
from pitchlog.db.engine import create_database_engine
from pitchlog.repositories import tenant_context_issuance, transaction

from .conftest import ProvisionedProductCatalog
from .test_product_authz_authn_app import (
    _app_dsn,
    _credential,
    _Identity,
    _login,
    _seed_identity,
    _seed_settings,
    _verify,
)

pytestmark = pytest.mark.requires_db


def _app_engine(app_dsn: str) -> Engine:
    """試験用のアプリロール接続資源を作る。"""
    options = conninfo_to_dict(app_dsn)
    return create_engine(
        URL.create(
            "postgresql+psycopg",
            username=str(options["user"]),
            password=str(options["password"]),
            host=str(options["host"]),
            port=int(str(options["port"])),
            database=str(options["dbname"]),
        ),
        connect_args={"sslmode": "disable", "gssencmode": "disable"},
    )


def _headers(value: str) -> dict[str, str]:
    """同じ提示値を Cookie と CSRF 条件とともに送る。"""
    return {
        "Cookie": f"__Host-pitchlog_token={value}",
        "X-Pitchlog-Request": "1",
        "Origin": "https://test",
    }


def _assert_same_response(*responses: Response) -> None:
    """HTTP 応答の状態・本文・全ヘッダが同一であることを確かめる。"""
    assert responses
    first = responses[0]
    for response in responses[1:]:
        assert response.status_code == first.status_code
        assert response.content == first.content
        assert response.headers.raw == first.headers.raw


@pytest.fixture(autouse=True)
def _configure_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """既存の非秘密固定試験素材と許可オリジンを設定する。"""
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(b"r" * 32).decode("ascii"),
    )
    monkeypatch.setenv("PITCHLOG_ALLOWED_ORIGINS", "https://test")


@pytest.mark.anyio
async def test_logout_entry_revokes_presented_token(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP ログアウトで Cookie を消し、同じ提示値を製品経路で拒否する。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    token_id = _login(identity)
    assert isinstance(token_id, UUID)
    app = create_app()
    presentation = app.state.token_presentation
    value = presentation.encode(token_id)
    engine = _app_engine(identity.app_dsn)
    monkeypatch.setattr(auth, "get_login_connection", lambda: engine)
    monkeypatch.setattr(
        tenant_context_issuance, "create_database_engine", lambda: engine
    )
    try:
        verified = verify_tenant_id(value, presentation, engine)
        assert verified is not None and verified[0] == identity.tenant_id
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://test"
        ) as client:
            result = await client.post("/auth/logout", headers=_headers(value))
            protected = await client.get("/players?limit=1", headers=_headers(value))

        assert result.status_code == 200
        assert result.json() == {"status": "logged_out"}
        assert "Max-Age=0" in result.headers["set-cookie"]
        assert protected.status_code == 401
        assert _verify(identity, token_id) is None
        assert verify_tenant_id(value, presentation, engine) is None
    finally:
        engine.dispose()


@pytest.mark.anyio
async def test_password_change_entry_records_change_and_revokes_old_tokens(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """現行 PW と変更日時を検査し、全旧トークンの失効を確かめる。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    token_ids = (_login(identity), _login(identity))
    assert all(isinstance(token_id, UUID) for token_id in token_ids)
    first_id, second_id = token_ids
    assert isinstance(first_id, UUID) and isinstance(second_id, UUID)
    app = create_app()
    presentation = app.state.token_presentation
    values = (presentation.encode(first_id), presentation.encode(second_id))
    engine = _app_engine(identity.app_dsn)
    monkeypatch.setattr(auth, "get_login_connection", lambda: engine)
    monkeypatch.setattr(
        tenant_context_issuance, "create_database_engine", lambda: engine
    )
    new_password = secrets.token_urlsafe(24) + "A1"
    before = _credential(catalog, identity.subject_id)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://test"
        ) as client:
            wrong = await client.patch(
                "/auth/password",
                json={"current_password": "wrong", "new_password": new_password},
                headers=_headers(values[0]),
            )
            policy = await client.patch(
                "/auth/password",
                json={
                    "current_password": identity.password,
                    "new_password": "short",
                },
                headers=_headers(values[0]),
            )
            assert wrong.status_code == 401
            assert policy.status_code == wrong.status_code
            assert policy.content == wrong.content
            assert _credential(catalog, identity.subject_id) == before

            changed = await client.patch(
                "/auth/password",
                json={
                    "current_password": identity.password,
                    "new_password": new_password,
                },
                headers=_headers(values[0]),
            )
            protected = await client.get(
                "/players?limit=1", headers=_headers(values[1])
            )
            missing = await client.patch(
                "/auth/password",
                json={
                    "current_password": identity.password,
                    "new_password": new_password,
                },
                headers=_headers(presentation.encode(uuid4())),
            )

        after = _credential(catalog, identity.subject_id)
        assert changed.status_code == 200
        assert changed.json() == {"status": "password_changed"}
        assert "Max-Age=0" in changed.headers["set-cookie"]
        assert "set-cookie" not in wrong.headers
        assert "token" not in changed.text
        assert new_password not in changed.text
        assert after[0] == before[0] + 1
        assert after[1] != before[1]
        assert after[2] > before[2]
        assert protected.status_code == 401
        assert missing.status_code == wrong.status_code
        assert missing.content == wrong.content
        for token_id, value in zip(token_ids, values, strict=True):
            assert isinstance(token_id, UUID)
            assert _verify(identity, token_id) is None
            assert verify_tenant_id(value, presentation, engine) is None
        assert isinstance(_login(identity, password=new_password), UUID)
        assert _login(identity) is None
    finally:
        engine.dispose()


@pytest.mark.anyio
async def test_password_change_entry_failure_reasons_have_identical_http_response(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """現行 PW・方針・無効値・期限・テナント状態の拒否を外部から比較する。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    identity = _seed_identity(catalog, app_dsn)
    disabled = _seed_identity(catalog, app_dsn)
    active_id, expired_id, disabled_id = (
        _login(identity),
        _login(identity),
        _login(disabled),
    )
    assert isinstance(active_id, UUID)
    assert isinstance(expired_id, UUID)
    assert isinstance(disabled_id, UUID)
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "UPDATE public.tenant_tokens "
            "SET last_used_at = pg_catalog.clock_timestamp() - interval '2 seconds', "
            "expires_at = pg_catalog.clock_timestamp() - interval '1 second' "
            "WHERE id = %s",
            (expired_id,),
        )
        cursor.execute(
            "UPDATE public.tenants SET enabled = false, "
            "disabled_at = pg_catalog.clock_timestamp() WHERE id = %s",
            (disabled.tenant_id,),
        )
    catalog.applicator.commit()

    app = create_app()
    presentation = app.state.token_presentation
    engine = _app_engine(app_dsn)
    monkeypatch.setattr(auth, "get_login_connection", lambda: engine)
    before = _credential(catalog, identity.subject_id)
    new_password = secrets.token_urlsafe(24) + "A1"
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://test"
        ) as client:
            wrong_current = await client.patch(
                "/auth/password",
                json={"current_password": "wrong", "new_password": new_password},
                headers=_headers(presentation.encode(active_id)),
            )
            invalid_new = await client.patch(
                "/auth/password",
                json={"current_password": identity.password, "new_password": "short"},
                headers=_headers(presentation.encode(active_id)),
            )
            unknown_token = await client.patch(
                "/auth/password",
                json={
                    "current_password": identity.password,
                    "new_password": new_password,
                },
                headers=_headers(presentation.encode(uuid4())),
            )
            expired_token = await client.patch(
                "/auth/password",
                json={
                    "current_password": identity.password,
                    "new_password": new_password,
                },
                headers=_headers(presentation.encode(expired_id)),
            )
            disabled_tenant = await client.patch(
                "/auth/password",
                json={
                    "current_password": disabled.password,
                    "new_password": new_password,
                },
                headers=_headers(presentation.encode(disabled_id)),
            )

        assert wrong_current.status_code == 401
        _assert_same_response(
            wrong_current, invalid_new, unknown_token, expired_token, disabled_tenant
        )
        assert "set-cookie" not in wrong_current.headers
        assert _credential(catalog, identity.subject_id) == before
    finally:
        engine.dispose()


@pytest.mark.anyio
async def test_logout_entry_response_is_independent_of_presented_token_state(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """有効・失効済み・署名不正の提示値で同じ HTTP 応答を返す。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    identity = _seed_identity(catalog, _app_dsn(catalog))
    token_id = _login(identity)
    assert isinstance(token_id, UUID)
    app = create_app()
    value = app.state.token_presentation.encode(token_id)
    engine = _app_engine(identity.app_dsn)
    monkeypatch.setattr(auth, "get_login_connection", lambda: engine)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://test"
        ) as client:
            valid = await client.post("/auth/logout", headers=_headers(value))
            revoked = await client.post("/auth/logout", headers=_headers(value))
            bad_signature = await client.post(
                "/auth/logout", headers=_headers(f"broken.{value}")
            )

        assert valid.status_code == 200
        _assert_same_response(valid, revoked, bad_signature)
        assert valid.json() == {"status": "logged_out"}
        assert "Max-Age=0" in valid.headers["set-cookie"]
        assert value not in valid.text
        assert _verify(identity, token_id) is None
    finally:
        engine.dispose()


@pytest.mark.anyio
async def test_password_change_entry_cannot_use_another_tenants_password(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A の提示値と B の現行 PW を混ぜても両テナントを変更しない。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    first = _seed_identity(catalog, app_dsn)
    second = _seed_identity(catalog, app_dsn)
    first_id, second_id = _login(first), _login(second)
    assert isinstance(first_id, UUID) and isinstance(second_id, UUID)
    first_before = _credential(catalog, first.subject_id)
    second_before = _credential(catalog, second.subject_id)
    app = create_app()
    presentation = app.state.token_presentation
    first_value = presentation.encode(first_id)
    second_value = presentation.encode(second_id)
    engine = _app_engine(app_dsn)
    monkeypatch.setenv(
        "PITCHLOG_DATABASE_URL",
        engine.url.set(query={"sslmode": "disable"}).render_as_string(
            hide_password=False
        ),
    )
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")
    monkeypatch.setattr(auth, "get_login_connection", lambda: engine)
    monkeypatch.setattr(
        tenant_context_issuance, "create_database_engine", lambda: engine
    )
    new_password = secrets.token_urlsafe(24) + "A1"
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://test"
        ) as client:
            crossed = await client.patch(
                "/auth/password",
                json={
                    "current_password": second.password,
                    "new_password": new_password,
                },
                headers=_headers(first_value),
            )
            second_access = await client.get(
                "/players?limit=1",
                headers={
                    **_headers(second_value),
                    "X-Pitchlog-Expected-Tenant": str(second.tenant_id),
                    "X-Pitchlog-Tenant-Challenge": str(uuid4()),
                },
            )

        assert crossed.status_code == 401
        assert "set-cookie" not in crossed.headers
        assert second_access.status_code == 200
        assert _credential(catalog, first.subject_id) == first_before
        assert _credential(catalog, second.subject_id) == second_before
        assert _verify(first, first_id) == first.tenant_id
        assert _verify(second, second_id) == second.tenant_id
    finally:
        engine.dispose()


@pytest.mark.anyio
async def test_logout_entry_revokes_only_the_presented_tenant_token(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A の提示値によるログアウト後も B の経路を使える。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    first = _seed_identity(catalog, app_dsn)
    second = _seed_identity(catalog, app_dsn)
    first_id, second_id = _login(first), _login(second)
    assert isinstance(first_id, UUID) and isinstance(second_id, UUID)
    app = create_app()
    presentation = app.state.token_presentation
    first_value = presentation.encode(first_id)
    second_value = presentation.encode(second_id)
    engine = _app_engine(app_dsn)
    monkeypatch.setenv(
        "PITCHLOG_DATABASE_URL",
        engine.url.set(query={"sslmode": "disable"}).render_as_string(
            hide_password=False
        ),
    )
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")
    monkeypatch.setattr(auth, "get_login_connection", lambda: engine)
    monkeypatch.setattr(
        tenant_context_issuance, "create_database_engine", lambda: engine
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://test"
        ) as client:
            first_logout = await client.post(
                "/auth/logout", headers=_headers(first_value)
            )
            first_access = await client.get(
                "/players?limit=1", headers=_headers(first_value)
            )
            second_access = await client.get(
                "/players?limit=1",
                headers={
                    **_headers(second_value),
                    "X-Pitchlog-Expected-Tenant": str(second.tenant_id),
                    "X-Pitchlog-Tenant-Challenge": str(uuid4()),
                },
            )

        assert first_logout.status_code == 200
        assert first_access.status_code == 401
        assert second_access.status_code == 200
        assert _verify(first, first_id) is None
        assert _verify(second, second_id) == second.tenant_id
    finally:
        engine.dispose()


_READ_RULE_ID = UUID("0a000000-0000-4000-8000-000000000001")


def _read_snapshot() -> dict[str, object]:
    """取得試験用の保存snapshotを返す。作成/出所証明の代用ではない。"""
    return {
        "ruleSetId": str(_READ_RULE_ID),
        "regulationInnings": 9,
        "coldConditions": [],
        "extensionLimit": 12,
        "tiebreak": {
            "startInning": 10,
            "runnerPlacement": "no_out_first_second",
            "leadoffRule": "continue_lineup",
        },
        "dh": True,
    }


@dataclass(repr=False)
class _PreparingReadDb:
    """一時資格をreprへ出さない実API read環境。"""

    catalog: ProvisionedProductCatalog
    identity: _Identity
    other: _Identity
    app: FastAPI
    engine: Engine
    teams: dict[UUID, UUID]
    events: list[str]


def _seed_read_game(
    db: _PreparingReadDb,
    number: int,
    *,
    tenant: UUID | None = None,
    snapshot: dict[str, object] | None = None,
    tournament: str = "read-cup",
    status: str = "preparing",
    hidden: bool = False,
    trashed: bool = False,
) -> UUID:
    """実SQLでread対象を準備する。製品の作成成功とは扱わない。"""
    tenant_id = db.identity.tenant_id if tenant is None else tenant
    game_id = UUID(int=number)
    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO public.games "
            "(tenant_id,id,scheduled_at,game_type_key,tournament_key,"
            "away_team_record_id,home_team_record_id,status,applied_rules,"
            "section_label,hidden_at,trashed_at) "
            "VALUES (%s,%s,%s,'game_official',%s,%s,%s,%s,%s::jsonb,%s,"
            "CASE WHEN %s THEN now() ELSE NULL END,"
            "CASE WHEN %s THEN now() ELSE NULL END)",
            (
                tenant_id,
                game_id,
                datetime(2026, 7, 22, 9, tzinfo=timezone.utc),
                tournament,
                db.teams[tenant_id],
                db.teams[tenant_id],
                status,
                json.dumps(_read_snapshot() if snapshot is None else snapshot),
                "<b>保存ラベル</b>",
                hidden,
                trashed,
            ),
        )
    db.catalog.applicator.commit()
    return game_id


@pytest.fixture
def preparing_read_database(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_PreparingReadDb]:
    """実login/署名/C2/scopeと正規app engineを接続する。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    identity = _seed_identity(catalog, app_dsn)
    other = _seed_identity(catalog, app_dsn)
    teams = {identity.tenant_id: uuid4(), other.tenant_id: uuid4()}
    with catalog.applicator.cursor() as cursor:
        for tenant, team in teams.items():
            cursor.execute(
                "INSERT INTO public.team_records(tenant_id,id,kind,name) "
                "VALUES (%s,%s,'opponent','相手')",
                (tenant, team),
            )
            for key in ("read-cup", ""):
                cursor.execute(
                    "INSERT INTO public.tenant_vocabularies "
                    "(tenant_id,key,category,display_name) "
                    "VALUES (%s,%s,'tournament','大会')",
                    (tenant, key),
                )
        cursor.execute(
            "INSERT INTO public.rule_sets "
            "(id,regulation_innings,called_game_conditions,extra_innings_limit,"
            "tiebreak_rule,uses_dh) VALUES (%s,9,'[]',12,%s::jsonb,true)",
            (_READ_RULE_ID, json.dumps(_read_snapshot()["tiebreak"])),
        )
    catalog.applicator.commit()
    options = conninfo_to_dict(app_dsn)
    app_url = URL.create(
        "postgresql+psycopg",
        username=str(options["user"]),
        password=str(options["password"]),
        host=str(options["host"]),
        port=int(str(options["port"])),
        database=str(options["dbname"]),
        query={"sslmode": "disable"},
    )
    monkeypatch.setenv(
        "PITCHLOG_DATABASE_URL", app_url.render_as_string(hide_password=False)
    )
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")
    engine = create_database_engine()
    events: list[str] = []
    event.listen(engine, "commit", lambda connection: events.append("commit"))
    event.listen(engine, "rollback", lambda connection: events.append("rollback"))

    def _observe(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        """games読取の発生だけを観測し、SQL/入力/資格を保存しない。"""
        if re.search(r"\bFROM\s+(?:public\.)?games\b", statement, re.I):
            events.append("games_sql")

    event.listen(engine, "before_cursor_execute", _observe)
    monkeypatch.setattr(auth, "get_login_connection", lambda: engine)
    monkeypatch.setattr(
        tenant_context_issuance, "create_database_engine", lambda: engine
    )
    monkeypatch.setattr(transaction, "create_database_engine", lambda: engine)
    try:
        db = _PreparingReadDb(
            catalog, identity, other, create_app(), engine, teams, events
        )
        for i in (1, 2, 3):
            _seed_read_game(db, i)
        _seed_read_game(db, 4, hidden=True)
        _seed_read_game(db, 5, trashed=True)
        _seed_read_game(db, 6, status="in_progress")
        _seed_read_game(db, 7, status="finished")
        _seed_read_game(db, 20, tenant=other.tenant_id)
        yield db
    finally:
        engine.dispose()


def _read_headers(tenant: UUID) -> dict[str, str]:
    """C2のexpected tenantと一意challengeを設定する。"""
    return {
        "X-Pitchlog-Expected-Tenant": str(tenant),
        "X-Pitchlog-Tenant-Challenge": str(uuid4()),
    }


async def _http_read_login(client: AsyncClient, identity: _Identity) -> None:
    """実POST loginが発行するCookieを同じclientへ保持する。"""
    response = await client.post(
        "/auth/login",
        json={"team_name": identity.name, "password": identity.password},
        headers={"Origin": "https://test", "X-Pitchlog-Request": "1"},
    )
    assert response.status_code == 200
    assert response.json()["tenant_id"] == str(identity.tenant_id)
    assert "Secure" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "__Host-pitchlog_token" in client.cookies


def _assert_read_metadata(
    response: Response, headers: dict[str, str], *, success: bool
) -> None:
    """全read応答のno-storeと成功時だけのACKを検査する。"""
    assert response.headers["cache-control"] == "no-store"
    if success:
        assert response.headers["X-Pitchlog-Tenant-Match"] == "1"
        assert (
            response.headers["X-Pitchlog-Tenant-Challenge"]
            == headers["X-Pitchlog-Tenant-Challenge"]
        )
    else:
        assert "X-Pitchlog-Tenant-Match" not in response.headers
        assert "X-Pitchlog-Tenant-Challenge" not in response.headers


@pytest.mark.anyio
async def test_preparing_read_real_login_paging_and_snapshot(
    preparing_read_database: _PreparingReadDb,
) -> None:
    """実login Cookieから同時刻ページング/詳細/非遡及を確認する。"""
    db = preparing_read_database
    async with AsyncClient(
        transport=ASGITransport(app=db.app), base_url="https://test"
    ) as client:
        await _http_read_login(client, db.identity)
        headers = _read_headers(db.identity.tenant_id)
        page = await client.get("/games?limit=2", headers=headers)
        assert page.status_code == 200
        _assert_read_metadata(page, headers, success=True)
        body = page.json()
        assert [x["id"] for x in body["items"]] == [str(UUID(int=3)), str(UUID(int=2))]
        assert body["next_cursor"]
        last = await client.get(
            "/games",
            params={"limit": 2, "cursor": body["next_cursor"]},
            headers=headers,
        )
        assert last.status_code == 200 and [x["id"] for x in last.json()["items"]] == [
            str(UUID(int=1))
        ]
        assert last.json()["next_cursor"] is None
        with db.catalog.applicator.cursor() as cursor:
            cursor.execute(
                "UPDATE public.rule_sets SET extra_innings_limit=10 WHERE id=%s",
                (_READ_RULE_ID,),
            )
        db.catalog.applicator.commit()
        detail = await client.get(f"/games/{UUID(int=3)}", headers=headers)
        assert detail.status_code == 200
        assert detail.json() == body["items"][0]
        assert detail.json()["status"] == "preparing"
        assert detail.json()["applied_rules"] == _read_snapshot()
        assert detail.json()["section_label"] == "<b>保存ラベル</b>"
        assert detail.headers["content-type"].startswith("application/json")
        _assert_read_metadata(detail, headers, success=True)


@pytest.mark.anyio
async def test_preparing_read_auth_and_c2_precede_query_sql(
    preparing_read_database: _PreparingReadDb,
) -> None:
    """未認証/不正metadataは不正query/pathやgames SQLより前に拒否する。"""
    db = preparing_read_database
    async with AsyncClient(
        transport=ASGITransport(app=db.app), base_url="https://test"
    ) as client:
        headers = _read_headers(db.identity.tenant_id)
        missing = await client.get("/games?limit=bad", headers=headers)
        assert missing.status_code == 401
        _assert_read_metadata(missing, headers, success=False)
        wrong = await client.post(
            "/auth/login",
            json={"team_name": db.identity.name, "password": "invalid-password"},
        )
        assert wrong.status_code == 401
        client.cookies.set("__Host-pitchlog_token", "invalid-presentation")
        invalid = await client.get("/games", headers=headers)
        assert invalid.status_code == 401
        client.cookies.clear()
        await _http_read_login(client, db.identity)
        count = db.events.count("games_sql")
        variants: list[Any] = [
            {},
            {**headers, "X-Pitchlog-Expected-Tenant": str(db.other.tenant_id)},
            {**headers, "X-Pitchlog-Tenant-Challenge": "bad"},
            {
                **headers,
                "X-Pitchlog-Expected-Tenant": str(db.identity.tenant_id).replace(
                    "-", ""
                ),
            },
            [
                *headers.items(),
                ("X-Pitchlog-Expected-Tenant", str(db.identity.tenant_id)),
            ],
        ]
        for metadata in variants:
            response = await client.get("/games/not-a-uuid?limit=bad", headers=metadata)
            assert response.status_code == 404
            _assert_read_metadata(response, headers, success=False)
        for path in (
            "/games?limit=0",
            "/games?limit=101",
            "/games?cursor=bad",
            "/games?status=finished",
            "/games/not-a-uuid",
        ):
            response = await client.get(path, headers=headers)
            assert response.status_code == 422
            _assert_read_metadata(response, headers, success=False)
        assert db.events.count("games_sql") == count
        logout = await client.post(
            "/auth/logout",
            headers={"Origin": "https://test", "X-Pitchlog-Request": "1"},
        )
        assert logout.status_code == 200
        denied = await client.get("/games", headers=headers)
        assert denied.status_code == 401


@pytest.mark.anyio
async def test_preparing_read_invisible_details_are_uniform(
    preparing_read_database: _PreparingReadDb,
) -> None:
    """他tenant/不存在/非表示/ゴミ箱/他状態を同じ404へ閉じる。"""
    db = preparing_read_database
    async with AsyncClient(
        transport=ASGITransport(app=db.app), base_url="https://test"
    ) as client:
        await _http_read_login(client, db.identity)
        headers = _read_headers(db.identity.tenant_id)
        bodies = []
        for i in (4, 5, 6, 7, 20, 999):
            response = await client.get(f"/games/{UUID(int=i)}", headers=headers)
            assert response.status_code == 404
            _assert_read_metadata(response, headers, success=False)
            bodies.append(response.content)
        assert len(set(bodies)) == 1
    async with AsyncClient(
        transport=ASGITransport(app=db.app), base_url="https://test"
    ) as other_client:
        await _http_read_login(other_client, db.other)
        own = await other_client.get(
            "/games", headers=_read_headers(db.other.tenant_id)
        )
        assert own.status_code == 200
        assert [x["id"] for x in own.json()["items"]] == [str(UUID(int=20))]


@pytest.mark.anyio
async def test_preparing_read_invalid_saved_values_roll_back(
    preparing_read_database: _PreparingReadDb,
) -> None:
    """旧/壊れsnapshotとDTO不正をwith内で拒否しrollback後503にする。"""
    db = preparing_read_database
    five = dict(_read_snapshot())
    del five["ruleSetId"]
    corrupt = dict(_read_snapshot())
    corrupt["dh"] = 1
    async with AsyncClient(
        transport=ASGITransport(app=db.app), base_url="https://test"
    ) as client:
        await _http_read_login(client, db.identity)
        headers = _read_headers(db.identity.tenant_id)
        cases = [
            ({}, "read-cup"),
            (five, "read-cup"),
            (corrupt, "read-cup"),
            (_read_snapshot(), ""),
        ]
        for index, (snapshot, tournament) in enumerate(cases, 100):
            game_id = _seed_read_game(
                db, index, snapshot=snapshot, tournament=tournament
            )
            for path in (f"/games/{game_id}", "/games?limit=1"):
                response = await client.get(path, headers=headers)
                assert response.status_code == 503
                _assert_read_metadata(response, headers, success=False)
                assert db.events[-2:] == ["games_sql", "rollback"]
        good = await client.get(f"/games/{UUID(int=1)}", headers=headers)
        assert good.status_code == 200


@pytest.mark.anyio
async def test_preparing_read_real_select_denial_is_sanitized(
    preparing_read_database: _PreparingReadDb, caplog: pytest.LogCaptureFixture
) -> None:
    """実SELECT拒否を固定503へ写し、内部SQL/原例外を公開しない。"""
    db = preparing_read_database
    async with AsyncClient(
        transport=ASGITransport(app=db.app), base_url="https://test"
    ) as client:
        await _http_read_login(client, db.identity)
        with db.catalog.applicator.cursor() as cursor:
            cursor.execute("REVOKE SELECT ON public.games FROM pitchlog_app")
        db.catalog.applicator.commit()
        before = db.events.count("games_sql")
        response = await client.get(
            "/games", headers=_read_headers(db.identity.tenant_id)
        )
        assert response.status_code == 503
        assert db.events[-2:] == ["games_sql", "rollback"]
        assert db.events.count("games_sql") == before + 1
        assert "permission denied" not in response.text + caplog.text
        assert "SELECT games" not in response.text + caplog.text
        _assert_read_metadata(
            response, _read_headers(db.identity.tenant_id), success=False
        )
