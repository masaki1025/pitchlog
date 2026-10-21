"""使い捨て製品DBで自チーム読み取りと既存RLSを検査する。"""

from __future__ import annotations

from uuid import UUID, uuid4

import psycopg
import pytest
from db_fixtures import ProvisionedProductCatalog, _product_migration_url
from test_authz_tenant_context import make_tenant_context

from db.test_product_authz_authn_app import _app_dsn
from pitchlog.repositories.roster import SelfTeamRecordReadToken, TeamRecordReadToken
from pitchlog.repositories.transaction import tenant_transaction_scope

pytestmark = pytest.mark.requires_db


def _visible_teams(
    connection: psycopg.Connection[tuple[object, ...]], tenant_id: UUID | None
) -> tuple[tuple[object, ...], ...]:
    """App roleのtransaction-local文脈で見える行を返す。"""
    try:
        with connection.cursor() as cursor:
            if tenant_id is not None:
                cursor.execute(
                    "SELECT pg_catalog.set_config('app.tenant_id', %s, true)",
                    (str(tenant_id),),
                )
            cursor.execute("SELECT id, kind, name FROM team_records ORDER BY id")
            return tuple(tuple(row) for row in cursor.fetchall())
    finally:
        connection.rollback()


def test_self_read_and_rls_in_disposable_product_database(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A/Bのself・opponent、selfなし、重複拒否とapp roleのRLSを検査する。"""
    catalog = provisioned_product_catalog
    app_dsn = _app_dsn(catalog)
    tenant_a, tenant_b, tenant_c = uuid4(), uuid4(), uuid4()
    self_a, self_b = uuid4(), uuid4()
    opponent_a, opponent_b, opponent_c = uuid4(), uuid4(), uuid4()
    with catalog.applicator.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO tenants (id, name) VALUES (%s, %s)",
            ((tenant_a, "A"), (tenant_b, "B"), (tenant_c, "C")),
        )
        cursor.executemany(
            "INSERT INTO team_records (tenant_id, id, kind, name) "
            "VALUES (%s, %s, %s, %s)",
            (
                (tenant_a, self_a, "self", "A自チーム"),
                (tenant_a, opponent_a, "opponent", "A対戦相手"),
                (tenant_b, self_b, "self", "B自チーム"),
                (tenant_b, opponent_b, "opponent", "B対戦相手"),
                (tenant_c, opponent_c, "opponent", "C対戦相手"),
            ),
        )
    catalog.applicator.commit()

    with catalog.applicator.cursor() as cursor:
        with pytest.raises(psycopg.errors.UniqueViolation) as duplicate:
            cursor.execute(
                "INSERT INTO team_records (tenant_id, id, kind, name) "
                "VALUES (%s, %s, 'self', %s)",
                (tenant_a, uuid4(), "重複自チーム"),
            )
        assert duplicate.value.diag.constraint_name == "uq_team_records_self"
    catalog.applicator.rollback()

    monkeypatch.setenv(
        "PITCHLOG_DATABASE_URL", f"{_product_migration_url(app_dsn)}?sslmode=disable"
    )
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")
    for tenant_id, expected in (
        (tenant_a, ((self_a, "self", "A自チーム", None),)),
        (tenant_b, ((self_b, "self", "B自チーム", None),)),
        (tenant_c, ()),
    ):
        with tenant_transaction_scope(make_tenant_context(tenant_id)) as scope:
            assert scope.run(SelfTeamRecordReadToken()).rows == expected

    with tenant_transaction_scope(make_tenant_context(tenant_a)) as scope:
        opponents = scope.run(TeamRecordReadToken(limit=2)).rows
        assert opponents == ((opponent_a, "opponent", "A対戦相手", None),)

    with psycopg.connect(app_dsn) as connection:
        assert _visible_teams(connection, None) == ()
        assert set(_visible_teams(connection, tenant_a)) == {
            (self_a, "self", "A自チーム"),
            (opponent_a, "opponent", "A対戦相手"),
        }
        assert set(_visible_teams(connection, tenant_b)) == {
            (self_b, "self", "B自チーム"),
            (opponent_b, "opponent", "B対戦相手"),
        }
