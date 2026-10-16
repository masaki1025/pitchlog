"""テナント表示情報の固定read operationを製品DBで検証する。"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from sqlalchemy.engine import URL
from test_authz_tenant_context import make_tenant_context

from pitchlog.authz.runtime_contract import APPLICATION_ROLE_NAME
from pitchlog.repositories.tenant_profile import TenantProfileReadToken
from pitchlog.repositories.transaction import tenant_transaction_scope

from .conftest import ProvisionedProductCatalog

pytestmark = pytest.mark.requires_db


@dataclass(frozen=True, slots=True)
class _TenantProfileDatabase:
    """2テナントとapplication role接続先を保持する。"""

    tenant_a: UUID
    tenant_b: UUID
    name_a: str
    name_b: str
    app_dsn: str


def _application_url(dsn: str) -> str:
    """Libpq DSNを製品engineが使うSQLAlchemy URLへ変換する。"""
    values = conninfo_to_dict(dsn)
    return URL.create(
        "postgresql+psycopg",
        username=str(values["user"]),
        password=str(values["password"]),
        host=str(values["host"]),
        port=int(str(values["port"])),
        database=str(values["dbname"]),
        query={"sslmode": "disable"},
    ).render_as_string(hide_password=False)


@pytest.fixture
def tenant_profile_database(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> _TenantProfileDatabase:
    """製品認可適用済みDBへ異なる名称の2テナントを作る。"""
    catalog = provisioned_product_catalog
    tenant_a, tenant_b = uuid4(), uuid4()
    name_a, name_b = "テナントA", "テナントB"
    password = secrets.token_urlsafe(24)
    with catalog.applicator.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO tenants (id, name, enabled) VALUES (%s, %s, true)",
            ((tenant_a, name_a), (tenant_b, name_b)),
        )
        cursor.execute(
            sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                sql.Identifier(APPLICATION_ROLE_NAME),
                sql.Literal(password),
            )
        )
    catalog.applicator.commit()

    app_dsn = make_conninfo(
        catalog.owner_dsn,
        user=APPLICATION_ROLE_NAME,
        password=password,
    )
    monkeypatch.setenv("PITCHLOG_DATABASE_URL", _application_url(app_dsn))
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")
    return _TenantProfileDatabase(tenant_a, tenant_b, name_a, name_b, app_dsn)


def _visible_profiles(
    connection: psycopg.Connection[tuple[object, ...]], tenant_id: UUID | None
) -> tuple[tuple[object, ...], ...]:
    """transaction-local文脈の下で可視なテナント行を返す。"""
    try:
        with connection.cursor() as cursor:
            if tenant_id is not None:
                cursor.execute(
                    "SELECT pg_catalog.set_config('app.tenant_id', %s, true)",
                    (str(tenant_id),),
                )
            cursor.execute("SELECT id, name FROM tenants ORDER BY id")
            return tuple(tuple(row) for row in cursor.fetchall())
    finally:
        connection.rollback()


def test_tenant_profile_rls_and_application_role_select_are_effective(
    tenant_profile_database: _TenantProfileDatabase,
) -> None:
    """App roleのSELECTとFORCE RLSが2接続を各自の1行へ閉じる。"""
    db = tenant_profile_database
    with (
        psycopg.connect(db.app_dsn) as connection_a,
        psycopg.connect(db.app_dsn) as connection_b,
    ):
        with connection_a.cursor() as cursor:
            cursor.execute(
                "SELECT current_user, "
                "pg_catalog.has_table_privilege(current_user, 'public.tenants', "
                "'SELECT')"
            )
            assert cursor.fetchone() == (APPLICATION_ROLE_NAME, True)
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity "
                "FROM pg_catalog.pg_class AS relation "
                "JOIN pg_catalog.pg_namespace AS namespace "
                "ON namespace.oid = relation.relnamespace "
                "WHERE namespace.nspname = 'public' AND relation.relname = 'tenants'"
            )
            assert cursor.fetchone() == (True, True)
        connection_a.rollback()

        assert _visible_profiles(connection_a, db.tenant_a) == (
            (db.tenant_a, db.name_a),
        )
        assert _visible_profiles(connection_b, db.tenant_b) == (
            (db.tenant_b, db.name_b),
        )
        assert _visible_profiles(connection_a, None) == ()


def test_tenant_profile_operation_returns_only_the_verified_tenant(
    tenant_profile_database: _TenantProfileDatabase,
) -> None:
    """実製品operationが文脈tenantのIDと正規表示名だけを返す。"""
    db = tenant_profile_database
    with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
        assert scope.run(TenantProfileReadToken()).rows == ((db.tenant_a, db.name_a),)
    with tenant_transaction_scope(make_tenant_context(db.tenant_b)) as scope:
        assert scope.run(TenantProfileReadToken()).rows == ((db.tenant_b, db.name_b),)
    with tenant_transaction_scope(make_tenant_context(uuid4())) as scope:
        assert scope.run(TenantProfileReadToken()).rows == ()
