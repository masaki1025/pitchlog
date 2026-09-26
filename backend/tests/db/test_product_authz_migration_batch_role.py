"""移行バッチ用ロールの有効時の形を実 PostgreSQL で検証する。"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid5

import psycopg
import pytest
from product_authz_other_profiles_cases import other_profile_seed_rows
from product_authz_tenant_owned_cases import (
    TENANT_A,
    SeedRow,
    insert_candidate,
    insert_statement,
)
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb

from pitchlog.authz.product_catalog import (
    ProductCatalogReport,
    _load_migration_batch_expectations,
    inspect_migration_batch_role_catalog,
    inspect_product_authz_catalog,
)

from .conftest import ProvisionedProductCatalog

pytestmark = pytest.mark.requires_db

_UUID_NAMESPACE = UUID("4a87afbd-4ae3-4c93-a53a-9a8d22bad95d")
_RECORDED_AT = datetime(2026, 9, 26, 15, 0, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class _ActiveMigrationRole:
    """試験中だけ有効化した移行バッチ用ロール。"""

    name: str
    oid: int
    dsn: str


def _id(label: str) -> UUID:
    """試験内で安定した UUID を返す。"""
    return uuid5(_UUID_NAMESPACE, label)


def _bootstrap_superuser_oid(catalog: ProvisionedProductCatalog) -> int:
    """Fixture の外部適用主体の OID を返す。"""
    try:
        with catalog.applicator.cursor() as cursor:
            cursor.execute(
                "SELECT oid FROM pg_catalog.pg_roles WHERE rolname = current_user"
            )
            row = cursor.fetchone()
        assert row is not None
        role_oid = row[0]
        assert isinstance(role_oid, int) and not isinstance(role_oid, bool)
        return role_oid
    finally:
        catalog.applicator.rollback()


def _inspect_active(
    connection: psycopg.Connection[Any],
    role_oid: int,
) -> ProductCatalogReport:
    """公開経路で有効時の形を検査し、読み取り transaction を閉じる。"""
    try:
        return inspect_migration_batch_role_catalog(
            connection,
            role_oid=role_oid,
        )
    finally:
        connection.rollback()


def _inspect_steady(catalog: ProvisionedProductCatalog) -> ProductCatalogReport:
    """公開経路で製品の定常状態を検査する。"""
    try:
        return inspect_product_authz_catalog(
            catalog.observer,
            privileged_role_oids=frozenset({_bootstrap_superuser_oid(catalog)}),
        )
    finally:
        catalog.observer.rollback()


def _assert_active_red(
    connection: psycopg.Connection[Any],
    role_oid: int,
    check_id: str,
) -> None:
    """有効時の公開検査が指定した面を不合格にすると表明する。"""
    report = inspect_migration_batch_role_catalog(connection, role_oid=role_oid)
    assert not report.ok
    assert check_id in {violation.check_id for violation in report.violations}


def _seed_dependencies(catalog: ProvisionedProductCatalog) -> None:
    """19 表の INSERT・UPDATE に必要な依存行を外部主体で作る。"""
    with catalog.applicator.cursor() as cursor:
        for row in other_profile_seed_rows():
            statement, params = insert_statement(row)
            cursor.execute(statement, params)
    catalog.applicator.commit()


def _current_database(cursor: psycopg.Cursor[Any]) -> str:
    """現在の DB 名を返す。"""
    cursor.execute("SELECT pg_catalog.current_database()")
    row = cursor.fetchone()
    assert row is not None and isinstance(row[0], str)
    return row[0]


def _privilege_sql(privilege: str) -> sql.SQL:
    """試験で使う閉じた権限名を SQL token へ変換する。"""
    if privilege == "INSERT":
        return sql.SQL("INSERT")
    if privilege == "SELECT":
        return sql.SQL("SELECT")
    if privilege == "UPDATE":
        return sql.SQL("UPDATE")
    if privilege == "USAGE":
        return sql.SQL("USAGE")
    if privilege == "CREATE":
        return sql.SQL("CREATE")
    raise AssertionError(f"未知の試験用権限: {privilege}")


def _grant_asset_permissions(
    cursor: psycopg.Cursor[Any],
    role_name: str,
) -> None:
    """資産の必要権限行列を試験用ロールへそのまま付与する。"""
    expectations = _load_migration_batch_expectations()
    database = _current_database(cursor)
    cursor.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(database),
            sql.Identifier(role_name),
        )
    )
    cursor.execute(
        sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
            sql.Identifier("public"),
            sql.Identifier(role_name),
        )
    )
    for schema_name, table, column, privilege, grantable in expectations.permissions:
        assert grantable is False
        if column:
            cursor.execute(
                sql.SQL("GRANT {} ({}) ON TABLE {} TO {}").format(
                    _privilege_sql(privilege),
                    sql.Identifier(column),
                    sql.Identifier(schema_name, table),
                    sql.Identifier(role_name),
                )
            )
        else:
            cursor.execute(
                sql.SQL("GRANT {} ON TABLE {} TO {}").format(
                    _privilege_sql(privilege),
                    sql.Identifier(schema_name, table),
                    sql.Identifier(role_name),
                )
            )


@contextmanager
def _active_migration_role(
    catalog: ProvisionedProductCatalog,
) -> Iterator[_ActiveMigrationRole]:
    """資産どおりの移行ロールを作り、最後に必ず削除する。"""
    role_name = f"pitchlog_migration_{secrets.token_hex(6)}"
    password = secrets.token_urlsafe(24)
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            sql.SQL(
                "CREATE ROLE {} WITH LOGIN NOSUPERUSER BYPASSRLS "
                "NOCREATEROLE NOCREATEDB NOREPLICATION NOINHERIT PASSWORD {}"
            ).format(sql.Identifier(role_name), sql.Literal(password))
        )
        _grant_asset_permissions(cursor, role_name)
        cursor.execute(
            "SELECT oid FROM pg_catalog.pg_roles WHERE rolname = %s",
            (role_name,),
        )
        row = cursor.fetchone()
    catalog.applicator.commit()
    assert row is not None
    role_oid = row[0]
    assert isinstance(role_oid, int) and not isinstance(role_oid, bool)
    dsn = make_conninfo(catalog.owner_dsn, user=role_name, password=password)
    try:
        yield _ActiveMigrationRole(role_name, role_oid, dsn)
    finally:
        catalog.observer.rollback()
        catalog.applicator.rollback()
        with catalog.applicator.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role_name))
            )
            cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role_name)))
        catalog.applicator.commit()


def _migration_insert_rows() -> tuple[SeedRow, ...]:
    """19 write_targets の最小 INSERT 行を依存順で返す。"""
    run_id = _id("migration-run")
    tenant_owned_targets = (
        "team_records",
        "players",
        "games",
        "lineup_memories",
        "game_lineups",
        "participation_intervals",
        "operation_events",
        "play_rows",
        "play_runners",
        "idempotency_ledger",
        "evacuated_event_originals",
        "recording_generations",
        "medical_notes",
        "migrated_final_lineups",
    )
    return (
        SeedRow(
            "tenants",
            {"id": _id("tenant"), "name": "step10-migration-tenant", "enabled": True},
        ),
        *(insert_candidate(table, TENANT_A) for table in tenant_owned_targets),
        SeedRow(
            "migration_runs",
            {
                "id": run_id,
                "source_counts": {},
                "generated_copy_counts": {},
                "validation_results": {},
            },
        ),
        SeedRow(
            "migration_quarantine",
            {
                "id": _id("quarantine"),
                "import_batch_id": run_id,
                "source_read_order": 10,
                "raw_payload": b"step10",
            },
        ),
        SeedRow(
            "migration_resolution_reports",
            {
                "id": _id("resolution"),
                "import_batch_id": run_id,
                "source_kind": "step10",
                "legacy_row_identifier": "step10-resolution",
                "issue": {},
            },
        ),
        SeedRow(
            "migration_warning_reports",
            {
                "id": _id("warning"),
                "import_batch_id": run_id,
                "source_kind": "step10",
                "legacy_row_identifier": "step10-warning",
                "warning_kind": "step10",
                "details": {},
            },
        ),
    )


def _exercise_minimum_operations(role: _ActiveMigrationRole) -> None:
    """19 表の INSERT・SELECT と必要な列 UPDATE を実際に通す。"""
    expectations = _load_migration_batch_expectations()
    rows = _migration_insert_rows()
    assert {row.table for row in rows} == set(expectations.write_targets)
    with psycopg.connect(role.dsn) as connection:
        with connection.cursor() as cursor:
            for row in rows:
                statement, params = insert_statement(row)
                cursor.execute(statement, params)
            for table in expectations.write_targets:
                cursor.execute(
                    sql.SQL("SELECT pg_catalog.count(*) FROM {}").format(
                        sql.Identifier("public", table)
                    )
                )
                count_row = cursor.fetchone()
                assert count_row is not None and int(count_row[0]) > 0, table

            update_permissions = tuple(
                permission
                for permission in expectations.permissions
                if permission[3] == "UPDATE"
            )
            for schema_name, table, column, _, _ in update_permissions:
                if column in {"generated_copy_counts", "validation_results"}:
                    value: object = Jsonb({"step": 10})
                else:
                    value = _RECORDED_AT
                cursor.execute(
                    sql.SQL("UPDATE {} SET {} = %s").format(
                        sql.Identifier(schema_name, table),
                        sql.Identifier(column),
                    ),
                    (value,),
                )
                assert cursor.rowcount > 0, (table, column)
        connection.commit()


def _set_local_role(cursor: psycopg.Cursor[Any], role_name: str) -> None:
    """現在の transaction だけで試験対象ロールへ切り替える。"""
    cursor.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role_name)))


def test_asset_role_performs_minimum_operations_and_matches_active_shape(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """資産どおりのロールは最小操作を通し、有効時の形と一致する。"""
    catalog = provisioned_product_catalog
    _seed_dependencies(catalog)
    with _active_migration_role(catalog) as role:
        report = _inspect_active(catalog.observer, role.oid)
        assert report.ok
        assert report.violations == ()
        _exercise_minimum_operations(role)

        with psycopg.connect(role.dsn) as connection:
            with connection.cursor() as cursor:
                with pytest.raises(psycopg.Error) as lineup_error:
                    cursor.execute(
                        "UPDATE public.lineup_memories SET lineup = '{}'::jsonb"
                    )
                assert lineup_error.value.sqlstate == "42501"
            connection.rollback()
            with connection.cursor() as cursor:
                with pytest.raises(psycopg.Error) as medical_error:
                    cursor.execute(
                        "UPDATE public.medical_notes SET content = 'forbidden'"
                    )
                assert medical_error.value.sqlstate == "42501"
            connection.rollback()

        steady_report = _inspect_steady(catalog)
        assert not steady_report.ok
        assert "PRODUCT-CATALOG:UNAUTHORIZED-LOGIN-BYPASSRLS" in {
            violation.check_id for violation in steady_report.violations
        }

    restored_report = _inspect_steady(catalog)
    assert restored_report.ok
    assert restored_report.violations == ()


def test_table_level_update_mutation_is_red_and_opens_forbidden_columns(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """表単位 UPDATE は検査を落とし、保護外の 2 列を書き換えられる。"""
    catalog = provisioned_product_catalog
    _seed_dependencies(catalog)
    with _active_migration_role(catalog) as role:
        try:
            with catalog.applicator.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        "GRANT UPDATE ON TABLE public.lineup_memories, "
                        "public.medical_notes TO {}"
                    ).format(sql.Identifier(role.name))
                )
                _assert_active_red(
                    catalog.applicator,
                    role.oid,
                    "MIGRATION-BATCH:TABLE-ACL",
                )
                _set_local_role(cursor, role.name)
                cursor.execute(
                    "UPDATE public.lineup_memories "
                    "SET lineup = '{\"mutated\": true}'::jsonb"
                )
                assert cursor.rowcount > 0
                cursor.execute("UPDATE public.medical_notes SET content = 'mutated'")
                assert cursor.rowcount > 0
        finally:
            catalog.applicator.rollback()


def test_delete_mutation_is_red(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """DELETE の追加を表 ACL exact-set が拒否する。"""
    catalog = provisioned_product_catalog
    with _active_migration_role(catalog) as role:
        try:
            with catalog.applicator.cursor() as cursor:
                cursor.execute(
                    sql.SQL("GRANT DELETE ON public.tenants TO {}").format(
                        sql.Identifier(role.name)
                    )
                )
            _assert_active_red(
                catalog.applicator,
                role.oid,
                "MIGRATION-BATCH:TABLE-ACL",
            )
        finally:
            catalog.applicator.rollback()


@pytest.mark.parametrize("member_kind", ["unrelated_login", "applicator"])
def test_membership_edge_mutations_are_red(
    provisioned_product_catalog: ProvisionedProductCatalog,
    member_kind: str,
) -> None:
    """無関係 LOGIN と適用主体から移行ロールへ至る辺を拒否する。"""
    catalog = provisioned_product_catalog
    with _active_migration_role(catalog) as role:
        try:
            with catalog.applicator.cursor() as cursor:
                if member_kind == "unrelated_login":
                    member_name = f"step10_member_{secrets.token_hex(4)}"
                    cursor.execute(
                        sql.SQL("CREATE ROLE {} LOGIN").format(
                            sql.Identifier(member_name)
                        )
                    )
                else:
                    cursor.execute("SELECT current_user")
                    row = cursor.fetchone()
                    assert row is not None and isinstance(row[0], str)
                    member_name = row[0]
                cursor.execute(
                    sql.SQL(
                        "GRANT {} TO {} WITH ADMIN FALSE, INHERIT FALSE, SET FALSE"
                    ).format(
                        sql.Identifier(role.name),
                        sql.Identifier(member_name),
                    )
                )
            _assert_active_red(
                catalog.applicator,
                role.oid,
                "MIGRATION-BATCH:MEMBERSHIPS",
            )
        finally:
            catalog.applicator.rollback()


def test_relation_ownership_mutation_is_red(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """移行ロールに表を所有させる変異を拒否する。"""
    catalog = provisioned_product_catalog
    with _active_migration_role(catalog) as role:
        try:
            with catalog.applicator.cursor() as cursor:
                cursor.execute(
                    sql.SQL("ALTER TABLE public.tenants OWNER TO {}").format(
                        sql.Identifier(role.name)
                    )
                )
            _assert_active_red(
                catalog.applicator,
                role.oid,
                "MIGRATION-BATCH:OWNERSHIP",
            )
        finally:
            catalog.applicator.rollback()


def test_out_of_target_security_definer_execute_mutation_is_red(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """対象外表へ書く SECURITY DEFINER 関数の直接実行権を拒否する。"""
    catalog = provisioned_product_catalog
    with _active_migration_role(catalog) as role:
        try:
            with catalog.applicator.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE FUNCTION public.step10_write_admin_log()
                    RETURNS void
                    LANGUAGE sql
                    SECURITY DEFINER
                    SET search_path = pg_catalog, pg_temp
                    AS $function$
                        INSERT INTO public.admin_operation_logs(
                            id, operation_kind, target
                        ) VALUES (
                            '90dbacb5-41cc-47fc-b2c5-c8034fb919e8'::uuid,
                            'step10',
                            '{}'::jsonb
                        )
                    $function$
                    """
                )
                cursor.execute(
                    "REVOKE ALL ON FUNCTION public.step10_write_admin_log() FROM PUBLIC"
                )
                cursor.execute(
                    sql.SQL(
                        "GRANT EXECUTE ON FUNCTION "
                        "public.step10_write_admin_log() TO {}"
                    ).format(sql.Identifier(role.name))
                )
            _assert_active_red(
                catalog.applicator,
                role.oid,
                "MIGRATION-BATCH:FUNCTION-EXECUTE",
            )
        finally:
            catalog.applicator.rollback()


def test_public_function_execute_mutation_is_red(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """既存関数へ PUBLIC EXECUTE を戻す変異を実効権限で拒否する。"""
    catalog = provisioned_product_catalog
    with _active_migration_role(catalog) as role:
        try:
            with catalog.applicator.cursor() as cursor:
                cursor.execute(
                    "GRANT EXECUTE ON FUNCTION "
                    "public.prevent_players_identity_update() TO PUBLIC"
                )
            _assert_active_red(
                catalog.applicator,
                role.oid,
                "MIGRATION-BATCH:FUNCTION-EXECUTE",
            )
        finally:
            catalog.applicator.rollback()


def test_default_function_execute_mutation_is_red(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """既定権限から付く関数 EXECUTE も実効権限として拒否する。"""
    catalog = provisioned_product_catalog
    with _active_migration_role(catalog) as role:
        try:
            with catalog.applicator.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                        "GRANT EXECUTE ON FUNCTIONS TO {}"
                    ).format(sql.Identifier(role.name))
                )
                cursor.execute(
                    "CREATE FUNCTION public.step10_default_execute() "
                    "RETURNS integer LANGUAGE sql AS 'SELECT 10'"
                )
                cursor.execute(
                    "REVOKE EXECUTE ON FUNCTION "
                    "public.step10_default_execute() FROM PUBLIC"
                )
            _assert_active_red(
                catalog.applicator,
                role.oid,
                "MIGRATION-BATCH:FUNCTION-EXECUTE",
            )
        finally:
            catalog.applicator.rollback()


@pytest.mark.parametrize(
    ("schema_name", "privilege"),
    [
        pytest.param("public", "CREATE", id="public-create"),
        pytest.param("authz_private", "USAGE", id="private-usage"),
        pytest.param("authz_private", "CREATE", id="private-create"),
    ],
)
def test_schema_acl_mutations_are_red(
    provisioned_product_catalog: ProvisionedProductCatalog,
    schema_name: str,
    privilege: str,
) -> None:
    """Public USAGE 以外の 3 種の schema ACL を拒否する。"""
    catalog = provisioned_product_catalog
    with _active_migration_role(catalog) as role:
        try:
            with catalog.applicator.cursor() as cursor:
                cursor.execute(
                    sql.SQL("GRANT {} ON SCHEMA {} TO {}").format(
                        _privilege_sql(privilege),
                        sql.Identifier(schema_name),
                        sql.Identifier(role.name),
                    )
                )
            _assert_active_red(
                catalog.applicator,
                role.oid,
                "MIGRATION-BATCH:SCHEMA-ACL",
            )
        finally:
            catalog.applicator.rollback()
