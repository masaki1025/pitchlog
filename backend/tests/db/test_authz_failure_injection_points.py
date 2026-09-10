"""資産由来の失敗点と、非原子的な適用の再収束を検証する。"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import sql
from psycopg.pq import TransactionStatus

from pitchlog.authz import provisioning as provisioning_module
from pitchlog.authz.catalog import CatalogReport, inspect_authz_catalog
from pitchlog.authz.ddl import DDLStatement
from pitchlog.authz.provisioning import ProvisioningError, apply_authz_ddl

from .conftest import ProvisionedCatalog
from .test_authz_runtime_positive import (
    _POSITIVE_CASES,
    _insert_runtime_fixture,
    _runtime_fixture_definition,
)

pytestmark = pytest.mark.requires_db

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FAILURE_INJECTION_POINTS_PATH = (
    REPOSITORY_ROOT / "contracts/authz/failure-injection-points.json"
)


def _injection_points() -> tuple[dict[str, object], ...]:
    """失敗注入点資産の行を型確認して返す。"""
    raw = json.loads(FAILURE_INJECTION_POINTS_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    points = raw.get("injection_points")
    assert isinstance(points, list)
    assert all(isinstance(point, dict) for point in points)
    return tuple(point for point in points if isinstance(point, dict))


def _string(value: object) -> str:
    """資産値が空でない文字列であることを確認する。"""
    assert isinstance(value, str) and value
    return value


def _positive_int(value: object) -> int:
    """資産値が正の整数であることを確認する。"""
    assert type(value) is int and value > 0
    return value


def _object_rows(value: object, label: str) -> tuple[dict[str, object], ...]:
    """資産値を object 行列として確認する。"""
    assert isinstance(value, list), f"{label}は配列でなければならない"
    assert all(isinstance(row, dict) for row in value), (
        f"{label}はobject配列でなければならない"
    )
    return tuple(row for row in value if isinstance(row, dict))


def _comparison_targets(point: dict[str, object]) -> tuple[str, ...]:
    """失敗注入点から比較面を重複なく導出する。"""
    raw_targets = point.get("comparison_targets")
    assert isinstance(raw_targets, list)
    assert all(isinstance(target, str) and target for target in raw_targets)
    targets = tuple(target for target in raw_targets if isinstance(target, str))
    assert targets
    assert len(targets) == len(set(targets))
    return targets


def _asset_role_ids(asset: dict[str, object]) -> tuple[str, ...]:
    """DDL 資産が宣言するロール ID を返す。"""
    return tuple(
        _string(row.get("role_id")) for row in _object_rows(asset.get("roles"), "roles")
    )


def _asset_schema_ids(asset: dict[str, object]) -> tuple[str, ...]:
    """DDL 資産が宣言する schema ID を返す。"""
    return tuple(
        _string(row.get("schema_id"))
        for row in _object_rows(asset.get("schemas"), "schemas")
    )


def _observe_role_memberships(
    connection: psycopg.Connection[Any], asset: dict[str, object]
) -> tuple[tuple[object, ...], ...]:
    """資産ロールに接続する ``pg_auth_members`` の辺と option を観測する。"""
    role_ids = _asset_role_ids(asset)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT granted.rolname,
                   member.rolname,
                   membership.admin_option,
                   membership.inherit_option,
                   membership.set_option
            FROM pg_catalog.pg_auth_members AS membership
            JOIN pg_catalog.pg_roles AS granted
              ON granted.oid = membership.roleid
            JOIN pg_catalog.pg_roles AS member
              ON member.oid = membership.member
            WHERE granted.rolname = ANY(%s)
               OR member.rolname = ANY(%s)
            ORDER BY 1, 2, 3, 4, 5
            """,
            (list(role_ids), list(role_ids)),
        )
        return tuple(tuple(row) for row in cursor.fetchall())


def _observe_default_acls(
    connection: psycopg.Connection[Any], asset: dict[str, object]
) -> tuple[tuple[object, ...], ...]:
    """資産ロールまたは schema に属する ``pg_default_acl`` を観測する。"""
    role_ids = _asset_role_ids(asset)
    schema_ids = _asset_schema_ids(asset)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT owner.rolname,
                   COALESCE(namespace.nspname, ''),
                   defaults.defaclobjtype,
                   COALESCE(grantee.rolname, 'PUBLIC'),
                   privilege.privilege_type,
                   privilege.is_grantable
            FROM pg_catalog.pg_default_acl AS defaults
            JOIN pg_catalog.pg_roles AS owner
              ON owner.oid = defaults.defaclrole
            LEFT JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = defaults.defaclnamespace
            CROSS JOIN LATERAL
                 pg_catalog.aclexplode(defaults.defaclacl) AS privilege
            LEFT JOIN pg_catalog.pg_roles AS grantee
              ON grantee.oid = privilege.grantee
            WHERE owner.rolname = ANY(%s)
               OR namespace.nspname = ANY(%s)
            ORDER BY 1, 2, 3, 4, 5, 6
            """,
            (list(role_ids), list(schema_ids)),
        )
        return tuple(tuple(row) for row in cursor.fetchall())


def _observe_fixture_data(
    connection: psycopg.Connection[Any], asset: dict[str, object]
) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """資産に列挙された全 probe 表の行を JSONB として観測する。"""
    observed: list[tuple[str, str, tuple[str, ...]]] = []
    for table in _object_rows(asset.get("tables"), "tables"):
        schema_id = _string(table.get("schema_id"))
        table_id = _string(table.get("table_id"))
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "SELECT pg_catalog.to_jsonb(target)::text "
                    "FROM {}.{} AS target ORDER BY 1"
                ).format(sql.Identifier(schema_id), sql.Identifier(table_id))
            )
            rows = tuple(str(row[0]) for row in cursor.fetchall())
        observed.append((schema_id, table_id, rows))
    return tuple(observed)


def _observe_comparison_target(target: str, catalog: ProvisionedCatalog) -> object:
    """資産語彙の比較面を対応する公開検査または実カタログで観測する。"""
    if target == "all_target_catalogs":
        return inspect_authz_catalog(
            catalog.admin,
            REPOSITORY_ROOT,
            reference_connection=catalog.reference_admin,
        )
    if target == "role_memberships":
        return _observe_role_memberships(catalog.admin, catalog.asset)
    if target == "default_acls":
        return _observe_default_acls(catalog.admin, catalog.asset)
    if target == "fixture_data":
        return _observe_fixture_data(catalog.admin, catalog.asset)
    raise AssertionError(f"未対応の比較面: {target}")


def _rollback_observation_transactions(catalog: ProvisionedCatalog) -> None:
    """観測接続を rollback し、再適用を妨げるロックがない状態にする。"""
    for connection in (catalog.admin, catalog.reference_admin):
        connection.rollback()
        assert connection.info.transaction_status == TransactionStatus.IDLE


def _observe_state(
    point: dict[str, object], catalog: ProvisionedCatalog
) -> dict[str, object]:
    """失敗注入点が要求する全比較面の状態を記録する。"""
    targets = _comparison_targets(point)
    try:
        observed = {
            target: _observe_comparison_target(target, catalog) for target in targets
        }
        assert set(observed) == set(targets)
        return observed
    finally:
        # probe 表を読んだ admin 接続を idle in transaction のまま残さない。
        _rollback_observation_transactions(catalog)


def _owner_role_ids(asset: dict[str, object]) -> tuple[str, ...]:
    """Object 所有者を資産順の重複なし ID 列として返す。"""
    owner_ids = (
        _string(row.get("owner_role_id"))
        for key in ("schemas", "tables", "functions")
        for row in _object_rows(asset.get(key), key)
    )
    return tuple(dict.fromkeys(owner_ids))


def _provisioner_role_id(asset: dict[str, object]) -> str:
    """外部 provisioner を role kind から一意に導出する。"""
    provisioners = tuple(
        row
        for row in _object_rows(asset.get("roles"), "roles")
        if row.get("role_kind") == "external_provisioner"
    )
    assert len(provisioners) == 1
    return _string(provisioners[0].get("role_id"))


def _open_reapplication_memberships(catalog: ProvisionedCatalog) -> None:
    """中断前に存在する SET・USAGE 経路を再適用用の状態として作る。"""
    provisioner_id = _provisioner_role_id(catalog.asset)
    with psycopg.connect(catalog.provisioner_dsn) as connection:
        with connection.cursor() as cursor:
            for owner_id in _owner_role_ids(catalog.asset):
                cursor.execute(
                    sql.SQL("GRANT {} TO {} WITH SET TRUE, INHERIT TRUE").format(
                        sql.Identifier(owner_id),
                        sql.Identifier(provisioner_id),
                    )
                )
        connection.commit()


class _InjectedCheckpointFailure(ProvisioningError):
    """資産指定 checkpoint の直後に送出するテスト側の例外。"""


def _point_id(point: dict[str, object]) -> str:
    """Pytest の case ID に失敗注入点 ID を使う。"""
    return _string(point.get("injection_point_id"))


def test_failure_injection_checkpoints_exist_in_provisioning_log(
    provisioned_catalog: ProvisionedCatalog,
) -> None:
    """資産の checkpoint 全件が要素内位置を保って実行ログに含まれる。"""
    points = _injection_points()
    checkpoints = provisioned_catalog.provisioning_result.checkpoints
    checkpoint_by_id = {
        checkpoint.checkpoint_id: checkpoint for checkpoint in checkpoints
    }
    expected_ids = {_string(point["checkpoint_id"]) for point in points}

    # 適用器の全ログは失敗注入点より広い。資産の全点が含まれることだけを要求する。
    assert expected_ids <= set(checkpoint_by_id)

    for point in points:
        checkpoint = checkpoint_by_id[_string(point["checkpoint_id"])]
        assert checkpoint.step_id == _string(point["step_id"])
        assert checkpoint.operation_kind == _string(point["operation_kind"])
        assert checkpoint.element_type == _string(point["element_type"])

        position_rule = point["position_rule"]
        assert isinstance(position_rule, dict)
        expected_element_ordinal = _positive_int(
            position_rule["command_ordinal_within_element"]
        )
        same_element_checkpoints = tuple(
            candidate
            for candidate in checkpoints
            if candidate.step_id == checkpoint.step_id
            and candidate.element_type == checkpoint.element_type
            and candidate.element_id == checkpoint.element_id
        )
        assert same_element_checkpoints[expected_element_ordinal - 1] == checkpoint


@pytest.mark.parametrize("injection_point", _injection_points(), ids=_point_id)
def test_failure_injection_converges_only_after_reapplication(
    provisioned_catalog: ProvisionedCatalog,
    monkeypatch: pytest.MonkeyPatch,
    injection_point: dict[str, object],
) -> None:
    """各失敗点の A/B/C を記録し、非原子的な中断状態から再収束する。"""
    fixture = _runtime_fixture_definition(_POSITIVE_CASES[0])
    _insert_runtime_fixture(provisioned_catalog, fixture)
    state_a = _observe_state(injection_point, provisioned_catalog)
    reports_a = tuple(
        value for value in state_a.values() if isinstance(value, CatalogReport)
    )
    assert reports_a and all(report.ok for report in reports_a)

    # 完走時に閉じる membership を再び開き、既存 fixture を保った再適用を始める。
    _open_reapplication_memberships(provisioned_catalog)
    checkpoint_id = _string(injection_point.get("checkpoint_id"))
    injected_checkpoints: list[str] = []
    original_record: Callable[[Any, Any, DDLStatement], None] = (
        provisioning_module._CheckpointRecorder.record
    )

    def fail_after_checkpoint(
        recorder: Any,
        step: Any,
        statement: DDLStatement,
    ) -> None:
        """実文の記録直後に、資産指定 checkpoint だけで失敗させる。"""
        original_record(recorder, step, statement)
        checkpoint = recorder.result().checkpoints[-1]
        if checkpoint.checkpoint_id == checkpoint_id:
            injected_checkpoints.append(checkpoint.checkpoint_id)
            raise _InjectedCheckpointFailure(
                f"checkpoint直後の失敗注入: {checkpoint.checkpoint_id}"
            )

    with monkeypatch.context() as injection:
        injection.setattr(
            provisioning_module._CheckpointRecorder,
            "record",
            fail_after_checkpoint,
        )
        with (
            psycopg.connect(provisioned_catalog.provisioner_dsn) as provisioner,
            pytest.raises(_InjectedCheckpointFailure),
        ):
            apply_authz_ddl(provisioner, REPOSITORY_ROOT)
    assert injected_checkpoints == [checkpoint_id]

    # B は再適用前に必ず観測する。失敗 transaction の rollback は、先行して
    # commit 済みの非原子的な状態まで正常化しない。
    state_b = _observe_state(injection_point, provisioned_catalog)
    reports_b = tuple(
        value for value in state_b.values() if isinstance(value, CatalogReport)
    )
    assert reports_b and all(not report.ok for report in reports_b)
    assert state_b != state_a
    for target in _comparison_targets(injection_point):
        if target == "fixture_data":
            assert state_b[target] == state_a[target]

    with psycopg.connect(provisioned_catalog.provisioner_dsn) as provisioner:
        apply_authz_ddl(provisioner, REPOSITORY_ROOT)
    state_c = _observe_state(injection_point, provisioned_catalog)

    assert state_c == state_a
