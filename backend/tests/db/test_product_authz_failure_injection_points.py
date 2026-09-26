"""製品適用・取り外しの故障注入点で transaction の原子性を検証する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from db_fixtures import _product_role_ids, _snapshot_product_catalog
from psycopg.pq import TransactionStatus

from pitchlog.authz import product_provisioning
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

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_FAILURE_INJECTION_POINTS_PATH = (
    _REPOSITORY_ROOT / "contracts/authz/product/failure-injection-points.json"
)


class _InjectedProductCheckpointFailure(RuntimeError):
    """資産指定の製品記録点で送出する試験用例外。"""


def _injection_points() -> tuple[dict[str, object], ...]:
    """故障注入点資産の行を型確認して返す。"""
    document = json.loads(_FAILURE_INJECTION_POINTS_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    points = document.get("injection_points")
    assert isinstance(points, list)
    assert all(isinstance(point, dict) for point in points)
    return tuple(point for point in points if isinstance(point, dict))


def _text(value: object, label: str) -> str:
    """値を空でない文字列として検証する。"""
    assert isinstance(value, str) and value, f"{label} は空でない文字列が必要"
    return value


def _positive_int(value: object, label: str) -> int:
    """値を正の整数として検証する。"""
    assert type(value) is int and value > 0, f"{label} は正の整数が必要"
    return value


def _point_id(point: dict[str, object]) -> str:
    """Pytest の case ID に故障注入点 ID を使う。"""
    return _text(point.get("injection_point_id"), "injection_point_id")


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


def _observe_product_catalog(
    catalog: ProvisionedProductCatalog,
    privileged_role_oid: int,
) -> ProductCatalogReport:
    """公開検査で製品カタログを観測し、読み取り transaction を閉じる。"""
    try:
        return inspect_product_authz_catalog(
            catalog.observer,
            privileged_role_oids=frozenset({privileged_role_oid}),
        )
    finally:
        catalog.observer.rollback()
        assert catalog.observer.info.transaction_status is TransactionStatus.IDLE


def _snapshot_catalog(
    catalog: ProvisionedProductCatalog,
) -> ProductCatalogSnapshot:
    """製品が変更し得る実カタログを記録して transaction を閉じる。"""
    try:
        return _snapshot_product_catalog(
            catalog.observer,
            _product_role_ids(catalog.asset),
        )
    finally:
        catalog.observer.rollback()
        assert catalog.observer.info.transaction_status is TransactionStatus.IDLE


def _assert_subject_restored_after_rollback(
    catalog: ProvisionedProductCatalog,
) -> None:
    """故障した同じ接続が IDLE で認証主体へ戻っていることを確かめる。"""
    assert catalog.applicator.info.transaction_status is TransactionStatus.IDLE
    with catalog.applicator.cursor() as cursor:
        cursor.execute("SELECT current_user::text, session_user::text")
        row = cursor.fetchone()
    catalog.applicator.rollback()
    assert catalog.applicator.info.transaction_status is TransactionStatus.IDLE
    assert row is not None
    assert row[0] == row[1]


@pytest.mark.parametrize("injection_point", _injection_points(), ids=_point_id)
def test_operation_failure_rolls_back_the_complete_product_catalog(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
    injection_point: dict[str, object],
) -> None:
    """適用5点・取り外し2点の A・rollback 後 B・再適用後 C が一致する。"""
    catalog = provisioned_product_catalog
    privileged_role_oid = _bootstrap_superuser_oid(catalog)
    state_a = _observe_product_catalog(catalog, privileged_role_oid)
    snapshot_a = _snapshot_catalog(catalog)
    assert state_a.ok

    operation = _text(injection_point.get("operation"), "operation")
    assert operation in {"apply", "unapply"}
    run_operation = (
        apply_product_authz_ddl if operation == "apply" else unapply_product_authz_ddl
    )
    checkpoint_id = _text(injection_point.get("checkpoint_id"), "checkpoint_id")
    sequence = _positive_int(injection_point.get("sequence"), "sequence")
    recorded_checkpoints: list[str] = []
    injected_checkpoints: list[str] = []

    def fail_at_asset_checkpoint(recorded_checkpoint_id: str) -> None:
        """本番経路が資産指定の記録点へ到達した直後に失敗させる。"""
        recorded_checkpoints.append(recorded_checkpoint_id)
        if recorded_checkpoint_id == checkpoint_id:
            injected_checkpoints.append(recorded_checkpoint_id)
            raise _InjectedProductCheckpointFailure(
                f"製品記録点直後の故障注入: {recorded_checkpoint_id}"
            )

    with monkeypatch.context() as injection:
        injection.setattr(
            product_provisioning,
            "_record_product_checkpoint",
            fail_at_asset_checkpoint,
        )
        with pytest.raises(_InjectedProductCheckpointFailure):
            run_operation(catalog.applicator)

    assert injected_checkpoints == [checkpoint_id]
    assert checkpoint_id in recorded_checkpoints
    assert f"product:{sequence}:after_rollback" in recorded_checkpoints
    _assert_subject_restored_after_rollback(catalog)

    state_b = _observe_product_catalog(catalog, privileged_role_oid)
    snapshot_b = _snapshot_catalog(catalog)
    assert state_b.ok
    assert state_b == state_a
    assert snapshot_b == snapshot_a

    apply_product_authz_ddl(catalog.applicator)
    state_c = _observe_product_catalog(catalog, privileged_role_oid)
    snapshot_c = _snapshot_catalog(catalog)
    assert state_c.ok
    assert state_c == state_a
    assert snapshot_c == snapshot_a
