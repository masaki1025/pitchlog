"""実RG1常閉から作成serviceが非成功で取引を終えることを確認する。"""

from __future__ import annotations

import base64
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import event
from sqlalchemy.engine import URL
from test_authz_tenant_context import make_tenant_context
from test_game_preparing_components import _create_payload

from pitchlog.api.app import create_app
from pitchlog.api.routers import auth
from pitchlog.api.schemas.games import PreparingGameCreate
from pitchlog.db.engine import create_database_engine
from pitchlog.repositories import tenant_context_issuance, transaction
from pitchlog.repositories.rg1 import RG1Unavailable
from pitchlog.services.game_creation import create_preparing_game

from .conftest import ProvisionedProductCatalog
from .test_api_auth_exit_entry import (
    _app_engine,
    _assert_read_metadata,
    _http_read_login,
    _read_headers,
)
from .test_product_authz_authn_app import _app_dsn, _seed_identity, _seed_settings

pytestmark = pytest.mark.requires_db


def test_create_service_real_closed_rg1_rolls_back_before_business_sql(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """migration/製品DDL/実app接続で拒否する。HTTP認証/保存成功の証明ではない。"""
    catalog = provisioned_product_catalog
    engine = _app_engine(_app_dsn(catalog))
    tenant_id = uuid4()
    statements: list[str] = []
    rollbacks: list[bool] = []

    @event.listens_for(engine, "before_cursor_execute")
    def observe(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    @event.listens_for(engine, "rollback")
    def observe_rollback(connection: Any) -> None:
        rollbacks.append(True)

    monkeypatch.setattr(transaction, "create_database_engine", lambda: engine)
    try:
        with pytest.raises(RG1Unavailable, match="閉じている"):
            with transaction.tenant_transaction_scope(
                make_tenant_context(tenant_id)
            ) as scope:
                create_preparing_game(
                    scope, PreparingGameCreate.model_validate(_create_payload())
                )
        assert any("rg1_api.rg1_read_open" in statement for statement in statements)
        assert not any("INSERT INTO" in statement.upper() for statement in statements)
        assert rollbacks
        with catalog.observer.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM public.games WHERE tenant_id = %s", (tenant_id,)
            )
            assert cursor.fetchone() == (0,)
            cursor.execute(
                "SELECT count(*) FROM public.tenant_vocabularies WHERE tenant_id = %s",
                (tenant_id,),
            )
            assert cursor.fetchone() == (0,)
    finally:
        catalog.observer.rollback()
        engine.dispose()


@pytest.mark.anyio
async def test_create_options_http_real_login_c2_and_closed_gate(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """正規engine/実loginからoptionsと常閉503へ到達し、認証を入力前に行う。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    identity = _seed_identity(catalog, app_dsn)
    other = _seed_identity(catalog, app_dsn)
    with catalog.applicator.cursor() as cursor:
        for key, category, disabled in (
            ("a", "tournament", False),
            ("b", "tournament", False),
            ("disabled", "tournament", True),
            ("strategy", "strategy", False),
        ):
            cursor.execute(
                "INSERT INTO public.tenant_vocabularies "
                "(tenant_id,key,category,display_name,disabled) "
                "VALUES (%s,%s,%s,%s,%s)",
                (identity.tenant_id, key, category, "<b>大会</b>", disabled),
            )
        cursor.execute(
            "INSERT INTO public.tenant_vocabularies "
            "(tenant_id,key,category,display_name) "
            "VALUES (%s,'other','tournament','他tenant')",
            (other.tenant_id,),
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
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64", base64.b64encode(b"r" * 32).decode("ascii")
    )
    monkeypatch.setenv("PITCHLOG_ALLOWED_ORIGINS", "https://test")
    engine = create_database_engine()
    monkeypatch.setattr(auth, "get_login_connection", lambda: engine)
    monkeypatch.setattr(
        tenant_context_issuance, "create_database_engine", lambda: engine
    )
    monkeypatch.setattr(transaction, "create_database_engine", lambda: engine)
    app = create_app()
    statements: list[str] = []
    rollbacks: list[bool] = []

    @event.listens_for(engine, "before_cursor_execute")
    def observe(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    @event.listens_for(engine, "rollback")
    def observe_rollback(connection: object) -> None:
        rollbacks.append(True)

    def business_sql() -> list[str]:
        return [
            sql
            for sql in statements
            if any(table in sql.lower() for table in ("tenant_vocabularies", "games"))
        ]

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://test"
        ) as client:
            unauthenticated = await client.post(
                "/games",
                content="{",
                headers={
                    "Origin": "https://test",
                    "X-Pitchlog-Request": "1",
                    "Content-Type": "application/json",
                },
            )
            assert unauthenticated.status_code == 401
            assert business_sql() == []
            await _http_read_login(client, identity)
            statements.clear()
            headers = _read_headers(identity.tenant_id)
            first = await client.get(
                "/games/preparation-options?limit=1", headers=headers
            )
            assert first.status_code == 200
            _assert_read_metadata(first, headers, success=True)
            body = first.json()
            assert body["tournaments"]["items"] == [
                {"key": "a", "display_name": "<b>大会</b>"}
            ]
            assert len(body["game_types"]) == 5
            second = await client.get(
                "/games/preparation-options",
                params={
                    "limit": 1,
                    "cursor": body["tournaments"]["next_cursor"],
                },
                headers=_read_headers(identity.tenant_id),
            )
            assert second.status_code == 200
            assert second.json()["tournaments"] == {
                "items": [{"key": "b", "display_name": "<b>大会</b>"}],
                "next_cursor": None,
            }
            for method, path in (
                ("GET", "/games/preparation-options?limit=wrong"),
                ("POST", "/games"),
            ):
                statements.clear()
                wrong_headers = {
                    **_read_headers(other.tenant_id),
                    "Origin": "https://test",
                    "X-Pitchlog-Request": "1",
                    "Content-Type": "application/json",
                }
                rejected = await client.request(
                    method, path, content="{", headers=wrong_headers
                )
                assert rejected.status_code == 404
                _assert_read_metadata(rejected, wrong_headers, success=False)
                assert business_sql() == []
            statements.clear()
            invalid = await client.post(
                "/games",
                content="{",
                headers={
                    **_read_headers(identity.tenant_id),
                    "Origin": "https://test",
                    "X-Pitchlog-Request": "1",
                    "Content-Type": "application/json",
                },
            )
            assert invalid.status_code == 422
            assert business_sql() == []
            statements.clear()
            rollbacks.clear()
            create_headers = {
                **_read_headers(identity.tenant_id),
                "Origin": "https://test",
                "X-Pitchlog-Request": "1",
            }
            rejected = await client.post(
                "/games",
                json={
                    **_create_payload(),
                    "tournament": {"kind": "new", "display_name": "新大会"},
                },
                headers=create_headers,
            )
            assert rejected.status_code == 503
            _assert_read_metadata(rejected, create_headers, success=False)
            assert business_sql() == []
            assert any("rg1_api.rg1_read_open" in sql for sql in statements)
            assert rollbacks
        with catalog.observer.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM public.games WHERE tenant_id=%s",
                (identity.tenant_id,),
            )
            assert cursor.fetchone() == (0,)
            cursor.execute(
                "SELECT count(*) FROM public.tenant_vocabularies WHERE tenant_id=%s",
                (identity.tenant_id,),
            )
            assert cursor.fetchone() == (4,)
    finally:
        catalog.observer.rollback()
        engine.dispose()
