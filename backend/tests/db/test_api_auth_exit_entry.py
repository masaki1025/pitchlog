"""ログアウトと PW 変更の HTTP 入口を実 DB に通して検査する。"""

import base64
import secrets
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient, Response
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL

from pitchlog.api.app import create_app
from pitchlog.api.routers import auth
from pitchlog.authz.verified_tenant import verify_tenant_id
from pitchlog.repositories import tenant_context_issuance

from .conftest import ProvisionedProductCatalog
from .test_product_authz_authn_app import (
    _app_dsn,
    _credential,
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
    """署名鍵と許可オリジンを試験ごとに設定する。"""
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
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
                "/players?limit=1", headers=_headers(second_value)
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
                "/players?limit=1", headers=_headers(second_value)
            )

        assert first_logout.status_code == 200
        assert first_access.status_code == 401
        assert second_access.status_code == 200
        assert _verify(first, first_id) is None
        assert _verify(second, second_id) == second.tenant_id
    finally:
        engine.dispose()
