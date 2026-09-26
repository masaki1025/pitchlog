"""製品認可 DDL の再適用・取り外し・migration 往復を検証する。"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from db_fixtures import _product_role_ids, _snapshot_product_catalog
from psycopg.pq import TransactionStatus

from pitchlog.authz.product_catalog import (
    ProductCatalogReport,
    inspect_product_authz_catalog,
)
from pitchlog.authz.product_provisioning import (
    apply_product_authz_ddl,
    unapply_product_authz_ddl,
)

from .conftest import ProductCatalogSnapshot, ProvisionedProductCatalog

pytestmark = pytest.mark.requires_db

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _bootstrap_superuser_oid(catalog: ProvisionedProductCatalog) -> int:
    """Fixture の外部適用主体である bootstrap superuser の OID を返す。"""
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            """
            SELECT role.oid
            FROM pg_catalog.pg_roles AS role
            WHERE role.rolname = current_user
            """
        )
        row = cursor.fetchone()
    catalog.applicator.rollback()
    assert catalog.applicator.info.transaction_status is TransactionStatus.IDLE
    assert row is not None
    role_oid = row[0]
    assert isinstance(role_oid, int) and not isinstance(role_oid, bool)
    return role_oid


def _inspect(
    catalog: ProvisionedProductCatalog,
    privileged_role_oid: int,
) -> ProductCatalogReport:
    """公開検査で製品カタログを観測して transaction を閉じる。"""
    try:
        return inspect_product_authz_catalog(
            catalog.observer,
            privileged_role_oids=frozenset({privileged_role_oid}),
        )
    finally:
        catalog.observer.rollback()
        assert catalog.observer.info.transaction_status is TransactionStatus.IDLE


def _snapshot(catalog: ProvisionedProductCatalog) -> ProductCatalogSnapshot:
    """製品が変更し得る実カタログを安定した行列として記録する。"""
    try:
        return _snapshot_product_catalog(
            catalog.observer,
            _product_role_ids(catalog.asset),
        )
    finally:
        catalog.observer.rollback()
        assert catalog.observer.info.transaction_status is TransactionStatus.IDLE


def _assert_subject_is_session(catalog: ProvisionedProductCatalog) -> None:
    """直前の製品操作後も外部適用主体が変わっていないことを確かめる。"""
    assert catalog.applicator.info.transaction_status is TransactionStatus.IDLE
    with catalog.applicator.cursor() as cursor:
        cursor.execute("SELECT current_user::text, session_user::text")
        row = cursor.fetchone()
    catalog.applicator.rollback()
    assert catalog.applicator.info.transaction_status is TransactionStatus.IDLE
    assert row is not None
    assert row[0] == row[1]


def _alembic_config() -> Config:
    """Fixture が設定した pitchlog_owner の URL を使う Alembic 設定を返す。"""
    return Config(str(_BACKEND_ROOT / "alembic.ini"))


def test_second_application_converges_to_the_first_catalog(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """Fixture の初回適用へ 2 回目の適用が exact に収束する。"""
    catalog = provisioned_product_catalog
    privileged_role_oid = _bootstrap_superuser_oid(catalog)
    first_report = _inspect(catalog, privileged_role_oid)
    first_snapshot = _snapshot(catalog)
    assert first_report.ok

    apply_product_authz_ddl(catalog.applicator)
    _assert_subject_is_session(catalog)

    second_report = _inspect(catalog, privileged_role_oid)
    second_snapshot = _snapshot(catalog)
    assert second_report.ok
    assert second_report == first_report
    assert second_snapshot == first_snapshot


def test_unapply_migration_round_trip_and_reapply_restore_both_catalogs(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """取り外し・migration 往復・再適用が各基準カタログへ戻る。"""
    catalog = provisioned_product_catalog
    privileged_role_oid = _bootstrap_superuser_oid(catalog)
    first_report = _inspect(catalog, privileged_role_oid)
    first_snapshot = _snapshot(catalog)
    assert first_report.ok

    unapply_product_authz_ddl(catalog.applicator)
    _assert_subject_is_session(catalog)
    unapplied_report = _inspect(catalog, privileged_role_oid)
    assert not unapplied_report.ok

    config = _alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    migration_report = _inspect(catalog, privileged_role_oid)
    migration_snapshot = _snapshot(catalog)
    assert migration_report == unapplied_report
    assert migration_snapshot == catalog.pre_application_catalog
    assert {row[2] for row in migration_snapshot.relations} == {"pitchlog_owner"}

    apply_product_authz_ddl(catalog.applicator)
    _assert_subject_is_session(catalog)
    reapplied_report = _inspect(catalog, privileged_role_oid)
    reapplied_snapshot = _snapshot(catalog)
    assert reapplied_report.ok
    assert reapplied_report == first_report
    assert reapplied_snapshot == first_snapshot


def test_reapplication_normalizes_a_dangerous_role_attribute_separately(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """危険な属性を足したケースだけで再適用による 7 属性の正規化を検証する。"""
    catalog = provisioned_product_catalog
    privileged_role_oid = _bootstrap_superuser_oid(catalog)
    expected_snapshot = _snapshot(catalog)

    with catalog.applicator.cursor() as cursor:
        cursor.execute("ALTER ROLE pitchlog_app BYPASSRLS")
    catalog.applicator.commit()

    dangerous_report = _inspect(catalog, privileged_role_oid)
    assert not dangerous_report.ok
    assert "PRODUCT-CATALOG:ROLES" in {
        violation.check_id for violation in dangerous_report.violations
    }

    apply_product_authz_ddl(catalog.applicator)
    normalized_report = _inspect(catalog, privileged_role_oid)
    normalized_snapshot = _snapshot(catalog)
    assert normalized_report.ok
    assert normalized_snapshot == expected_snapshot
