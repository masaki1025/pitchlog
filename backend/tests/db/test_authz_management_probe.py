"""代表管理関数の実行経路と認可失敗時の副作用不在を検証する。"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, Final

import psycopg
import pytest
from psycopg import sql

from .conftest import (
    ProvisionedCatalog,
    _authz_login_role_ids,
    _role_id,
)
from .test_authz_precondition_matrix import _assert_same_identifier_set, _only
from .test_authz_runtime_negative import _connection_role
from .test_authz_runtime_positive import (
    _grant_rows,
    _insert_runtime_fixture,
    _object_rows,
    _PositiveRuntimeFixture,
    _read_json_object,
    _string,
    _string_tuple,
)
from .test_authz_table_privileges import (
    _required_object,
    _table_privilege_contract,
    _TablePrivilegeContract,
)

pytestmark = pytest.mark.requires_db

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DDL_ELEMENTS_PATH = _REPOSITORY_ROOT / "contracts/authz/ddl-elements.json"
_MANAGEMENT_FUNCTION_BODY_PATH = (
    _REPOSITORY_ROOT / "contracts/authz/function-bodies/functions/"
    "apply_representative_grant_change.sql"
)
_MANAGEMENT_FUNCTION_CLASS = "representative_management_operation"
_ATOMIC_BOUNDARY_KIND = "authorization_and_side_effect"
_ATOMIC_STEP_IDS: Final[tuple[str, ...]] = (
    "authorize",
    "apply_effect",
    "record_effect",
)
_DENIED_EXECUTE_ROLE_KINDS: Final[tuple[str, ...]] = (
    "tested_caller",
    "negative_test_caller",
)
_DECISION_NOTE_RE = re.compile(r"-- DECISION: (?P<decision_id>[A-Z][A-Z0-9_]*)")


@dataclass(frozen=True, slots=True)
class _ManagementContract:
    """資産から導出した代表管理関数と実行ロールの契約。"""

    function_id: str
    schema_id: str
    calling_role_id: str
    executable_role_ids: frozenset[str]
    denied_execute_role_ids: frozenset[str]
    management_schema_function_ids: tuple[str, ...]
    table_privileges: _TablePrivilegeContract


@dataclass(frozen=True, slots=True)
class _ManagementFixture:
    """代表管理関数の認可入力と依存表の行を表す。"""

    requester_context_tenant_id: int | None
    membership_group_id: int
    membership_tenant_id: int
    membership_status: str
    membership_role: str
    grant_group_id: int
    grant_tenant_id: int
    grant_kind: str
    grant_enabled: bool
    invocation_group_id: int
    invocation_target_tenant_id: int
    invocation_effect_kind: str


@dataclass(frozen=True, slots=True)
class _AuthorizationFailureCase:
    """DECISION 条件を単独で偽にする fixture 変換。"""

    decision_id: str
    changed_field_id: str
    mutate: Callable[[_ManagementFixture], _ManagementFixture]


def _management_contract(asset: dict[str, object]) -> _ManagementContract:
    """代表管理関数と原子境界を資産から導出して検証する。

    Args:
        asset: DDL 要素資産。

    Returns:
        資産由来の代表管理関数契約。
    """
    probe = _required_object(
        asset.get("representative_management_probe"),
        "representative_management_probe",
    )
    function_id = _string(probe.get("function_id"), "management function_id")
    calling_role_id = _string(
        probe.get("calling_role_id"), "management calling_role_id"
    )

    functions = _object_rows(asset.get("functions"), "functions")
    all_function_ids = tuple(
        _string(row.get("function_id"), "functions.function_id") for row in functions
    )
    if len(all_function_ids) != len(set(all_function_ids)):
        raise AssertionError("functions.function_idが重複している")

    management_function_ids = frozenset(
        _string(row.get("function_id"), "management function_id")
        for row in functions
        if row.get("function_class") == _MANAGEMENT_FUNCTION_CLASS
    )
    _assert_same_identifier_set(
        management_function_ids,
        frozenset({function_id}),
        "代表管理操作とrepresentative_management_probe.function_id",
    )
    function = _required_object(
        _only(
            tuple(row for row in functions if row.get("function_id") == function_id),
            f"代表管理関数 {function_id}",
        ),
        f"代表管理関数 {function_id}",
    )
    schema_id = _string(function.get("schema_id"), f"{function_id}.schema_id")
    management_schema_function_ids = tuple(
        _string(row.get("function_id"), "management schema function_id")
        for row in functions
        if row.get("schema_id") == schema_id
    )
    _assert_same_identifier_set(
        frozenset(management_schema_function_ids),
        management_function_ids,
        f"{schema_id}の関数と代表管理操作",
    )

    executable_role_ids = frozenset(
        _string_tuple(
            function.get("execute_role_ids"), f"{function_id}.execute_role_ids"
        )
    )
    _assert_same_identifier_set(
        executable_role_ids,
        frozenset({calling_role_id}),
        "代表管理関数の実行ロールと呼び出しロール",
    )
    schema_usage_role_ids = frozenset(
        _string_tuple(
            function.get("caller_schema_usage_role_ids"),
            f"{function_id}.caller_schema_usage_role_ids",
        )
    )
    _assert_same_identifier_set(
        schema_usage_role_ids,
        executable_role_ids,
        "代表管理関数のschema到達ロールと実行ロール",
    )
    comparison_role_ids = frozenset(
        _role_id(asset, role_kind) for role_kind in _DENIED_EXECUTE_ROLE_KINDS
    )
    denied_execute_role_ids = comparison_role_ids - executable_role_ids
    _assert_same_identifier_set(
        denied_execute_role_ids,
        comparison_role_ids,
        "対照ロールと代表管理関数の実行拒否ロール",
    )

    if (
        function.get("owner_role_id") is None
        or function.get("security_mode") != "definer"
        or function.get("public_execute") is not False
        or function.get("return_contract") != "operation_result"
    ):
        raise AssertionError("代表管理関数の所有・実行・返却契約が一致しない")

    base_table_ids = frozenset(
        _string_tuple(probe.get("base_table_ids"), "management base_table_ids")
    )
    dependency_table_ids = frozenset(
        _string_tuple(
            function.get("dependency_table_ids"),
            f"{function_id}.dependency_table_ids",
        )
    )
    _assert_same_identifier_set(
        dependency_table_ids,
        base_table_ids,
        "代表管理関数の依存表とprobe基表",
    )

    table_privileges = _table_privilege_contract(asset)
    if (
        table_privileges.calling_role_id != calling_role_id
        or table_privileges.management_function_owner_id
        != function.get("owner_role_id")
        or table_privileges.table_id not in dependency_table_ids
    ):
        raise AssertionError("ステップ11の表権限契約と代表管理関数が一致しない")

    boundary_id = _string(
        probe.get("transaction_boundary_id"),
        "management transaction_boundary_id",
    )
    boundary = _required_object(
        _only(
            tuple(
                row
                for row in _object_rows(
                    asset.get("transaction_boundaries"), "transaction_boundaries"
                )
                if row.get("boundary_id") == boundary_id
            ),
            f"代表管理境界 {boundary_id}",
        ),
        f"代表管理境界 {boundary_id}",
    )
    boundary_step_ids = _string_tuple(
        boundary.get("step_ids"), f"{boundary_id}.step_ids"
    )
    if (
        boundary.get("boundary_kind") != _ATOMIC_BOUNDARY_KIND
        or boundary.get("atomic") is not True
        or boundary_step_ids != _ATOMIC_STEP_IDS
        or probe.get("authorization_and_side_effect_same_function") is not True
        or probe.get("authorization_and_side_effect_same_transaction") is not True
    ):
        raise AssertionError("代表管理関数の認可・副作用の原子境界が一致しない")

    return _ManagementContract(
        function_id=function_id,
        schema_id=schema_id,
        calling_role_id=calling_role_id,
        executable_role_ids=executable_role_ids,
        denied_execute_role_ids=denied_execute_role_ids,
        management_schema_function_ids=management_schema_function_ids,
        table_privileges=table_privileges,
    )


def _decision_ids_from_body() -> frozenset[str]:
    """凍結済み body の DECISION ノートを母集合として抽出する。

    Returns:
        body に存在する重複のない DECISION ID 集合。
    """
    body = _MANAGEMENT_FUNCTION_BODY_PATH.read_text(encoding="utf-8")
    decision_lines = tuple(
        line.strip() for line in body.splitlines() if "-- DECISION:" in line
    )
    decision_ids: list[str] = []
    for line in decision_lines:
        match = _DECISION_NOTE_RE.fullmatch(line)
        if match is None:
            raise AssertionError(f"DECISIONノートの構文が不正: {line}")
        decision_ids.append(match.group("decision_id"))
    if not decision_ids or len(decision_ids) != len(set(decision_ids)):
        raise AssertionError("管理関数のDECISIONノートが空または重複している")
    return frozenset(decision_ids)


def _baseline_management_fixture() -> _ManagementFixture:
    """全 DECISION 条件を満たす代表管理 fixture を返す。"""
    return _ManagementFixture(
        requester_context_tenant_id=12_001,
        membership_group_id=12_100,
        membership_tenant_id=12_001,
        membership_status="active",
        membership_role="admin",
        grant_group_id=12_100,
        grant_tenant_id=12_002,
        grant_kind="representative-grant-change",
        grant_enabled=True,
        invocation_group_id=12_100,
        invocation_target_tenant_id=12_002,
        invocation_effect_kind="representative-grant-change",
    )


def _without_requester_context(fixture: _ManagementFixture) -> _ManagementFixture:
    """要求元テナント GUC だけを未設定にする。"""
    return replace(fixture, requester_context_tenant_id=None)


def _outside_group_scope(fixture: _ManagementFixture) -> _ManagementFixture:
    """呼び出し先グループだけを所属行と不一致にする。"""
    return replace(fixture, invocation_group_id=12_101)


def _with_inactive_membership(fixture: _ManagementFixture) -> _ManagementFixture:
    """要求元 membership の有効状態だけを崩す。"""
    return replace(fixture, membership_status="inactive")


def _without_admin_role(fixture: _ManagementFixture) -> _ManagementFixture:
    """要求元 membership の管理ロールだけを崩す。"""
    return replace(fixture, membership_role="member")


def _outside_target_grant_scope(fixture: _ManagementFixture) -> _ManagementFixture:
    """呼び出し先テナントだけを grant 行と不一致にする。"""
    return replace(fixture, invocation_target_tenant_id=12_003)


def _with_mismatched_effect_kind(fixture: _ManagementFixture) -> _ManagementFixture:
    """呼び出しの副作用種別だけを grant 行と不一致にする。"""
    return replace(fixture, invocation_effect_kind="mismatched-effect-kind")


def _with_disabled_target_grant(fixture: _ManagementFixture) -> _ManagementFixture:
    """対象 grant の enabled だけを偽にする。"""
    return replace(fixture, grant_enabled=False)


def _with_mismatched_target_grant_group(
    fixture: _ManagementFixture,
) -> _ManagementFixture:
    """対象 grant のグループだけを membership 行と不一致にする。"""
    return replace(fixture, grant_group_id=12_101)


_BASELINE_FIXTURE = _baseline_management_fixture()
_AUTHORIZATION_FAILURE_CASES: Final[tuple[_AuthorizationFailureCase, ...]] = (
    _AuthorizationFailureCase(
        decision_id="MANAGEMENT_REQUESTER_CONTEXT_PRESENT",
        changed_field_id="requester_context_tenant_id",
        mutate=_without_requester_context,
    ),
    _AuthorizationFailureCase(
        decision_id="MANAGEMENT_GROUP_SCOPE",
        changed_field_id="invocation_group_id",
        mutate=_outside_group_scope,
    ),
    _AuthorizationFailureCase(
        decision_id="MANAGEMENT_REQUESTER_MEMBERSHIP_EFFECTIVE",
        changed_field_id="membership_status",
        mutate=_with_inactive_membership,
    ),
    _AuthorizationFailureCase(
        decision_id="MANAGEMENT_ADMIN_ROLE_REQUIRED",
        changed_field_id="membership_role",
        mutate=_without_admin_role,
    ),
    _AuthorizationFailureCase(
        decision_id="MANAGEMENT_TARGET_GRANT_SCOPE",
        changed_field_id="invocation_target_tenant_id",
        mutate=_outside_target_grant_scope,
    ),
    _AuthorizationFailureCase(
        decision_id="MANAGEMENT_EFFECT_KIND_MATCH",
        changed_field_id="invocation_effect_kind",
        mutate=_with_mismatched_effect_kind,
    ),
    _AuthorizationFailureCase(
        decision_id="MANAGEMENT_TARGET_GRANT_ENABLED",
        changed_field_id="grant_enabled",
        mutate=_with_disabled_target_grant,
    ),
    _AuthorizationFailureCase(
        decision_id="MANAGEMENT_TARGET_GRANT_GROUP_MATCH",
        changed_field_id="grant_group_id",
        mutate=_with_mismatched_target_grant_group,
    ),
)


def _assert_failure_case_contract() -> None:
    """Body 母集合と失敗ケースを exact-set 照合し単独変更も検査する。"""
    case_ids = tuple(case.decision_id for case in _AUTHORIZATION_FAILURE_CASES)
    if len(case_ids) != len(set(case_ids)):
        raise AssertionError("管理認可失敗ケースのdecision_idが重複している")
    _assert_same_identifier_set(
        frozenset(case_ids),
        _decision_ids_from_body(),
        "管理認可失敗ケースとbodyのDECISIONノート",
    )
    for case in _AUTHORIZATION_FAILURE_CASES:
        mutated = case.mutate(_BASELINE_FIXTURE)
        changed_field_ids = frozenset(
            field.name
            for field in fields(_ManagementFixture)
            if getattr(mutated, field.name) != getattr(_BASELINE_FIXTURE, field.name)
        )
        _assert_same_identifier_set(
            changed_field_ids,
            frozenset({case.changed_field_id}),
            f"{case.decision_id}の単独失敗入力",
        )


def _insert_management_fixture(
    catalog: ProvisionedCatalog, fixture: _ManagementFixture
) -> None:
    """ステップ 7 の共通投入ヘルパで管理関数 fixture を投入する。

    Args:
        catalog: 適用済みの使い捨て構成。
        fixture: 投入する認可入力行。
    """
    disabled_grant_kind = None
    if not fixture.grant_enabled:
        disabled_grant_kind = fixture.grant_kind
    runtime_fixture = _PositiveRuntimeFixture(
        requester_tenant_id=fixture.membership_tenant_id,
        granularity=_MANAGEMENT_FUNCTION_CLASS,
        groups=(),
        memberships=(
            (
                fixture.membership_group_id,
                fixture.membership_tenant_id,
                fixture.membership_status,
                fixture.membership_role,
            ),
        ),
        grants=_grant_rows(
            fixture.grant_group_id,
            (fixture.grant_tenant_id,),
            (fixture.grant_kind,),
            disabled_grant_kind=disabled_grant_kind,
        ),
        business_rows=(),
        invocations=(),
    )
    _insert_runtime_fixture(catalog, runtime_fixture)


def _invoke_management_function(
    connection: psycopg.Connection[Any],
    contract: _ManagementContract,
    fixture: _ManagementFixture,
) -> tuple[tuple[Any, ...], ...]:
    """実接続からテナント GUC と同一トランザクションで管理関数を呼ぶ。

    Args:
        connection: 呼び出し元ロール自身で認証した接続。
        contract: 呼び出す関数の資産由来契約。
        fixture: GUC と関数引数を持つ fixture。

    Returns:
        関数が返した行列。
    """
    with connection.cursor() as cursor:
        if fixture.requester_context_tenant_id is not None:
            cursor.execute(
                "SELECT pg_catalog.set_config('app.tenant_id', %s, true)",
                (str(fixture.requester_context_tenant_id),),
            )
        cursor.execute(
            sql.SQL("SELECT * FROM {}.{}(%s, %s, %s)").format(
                sql.Identifier(contract.schema_id),
                sql.Identifier(contract.function_id),
            ),
            (
                fixture.invocation_group_id,
                fixture.invocation_target_tenant_id,
                fixture.invocation_effect_kind,
            ),
        )
        return tuple(tuple(row) for row in cursor.fetchall())


def _effect_count(catalog: ProvisionedCatalog, contract: _ManagementContract) -> int:
    """副作用表の全行数を管理接続から直接取得する。"""
    with catalog.admin.cursor() as cursor:
        cursor.execute(
            sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                sql.Identifier(contract.table_privileges.schema_id),
                sql.Identifier(contract.table_privileges.table_id),
            )
        )
        row = cursor.fetchone()
    catalog.admin.rollback()
    if row is None or not isinstance(row[0], int):
        raise AssertionError("管理副作用表の行数を取得できない")
    return row[0]


def _management_function_oid(
    catalog: ProvisionedCatalog, contract: _ManagementContract
) -> int:
    """代表管理関数の OID を schema と関数 ID から一意に得る。"""
    with catalog.admin.cursor() as cursor:
        cursor.execute(
            """
            SELECT routine.oid
            FROM pg_catalog.pg_proc AS routine
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = routine.pronamespace
            WHERE namespace.nspname = %s
              AND routine.proname = %s
              AND routine.prokind = 'f'
            ORDER BY pg_catalog.pg_get_function_identity_arguments(routine.oid)
            """,
            (contract.schema_id, contract.function_id),
        )
        oid_rows = tuple(cursor.fetchall())
    catalog.admin.rollback()
    oid_row = _only(oid_rows, f"代表管理関数 {contract.function_id} のOID")
    if not isinstance(oid_row, tuple) or not oid_row or not isinstance(oid_row[0], int):
        raise AssertionError("代表管理関数のOIDが整数でない")
    return oid_row[0]


def _has_function_execute(
    catalog: ProvisionedCatalog, role_id: str, function_oid: int
) -> bool:
    """指定ロールの関数 EXECUTE 権限をカタログ関数で観測する。"""
    with catalog.admin.cursor() as cursor:
        cursor.execute(
            "SELECT pg_catalog.has_function_privilege(%s, %s, 'EXECUTE')",
            (role_id, function_oid),
        )
        row = cursor.fetchone()
    catalog.admin.rollback()
    if row is None or not isinstance(row[0], bool):
        raise AssertionError("関数EXECUTE権限を取得できない")
    return row[0]


def _has_schema_usage(
    catalog: ProvisionedCatalog, role_id: str, schema_id: str
) -> bool:
    """指定ロールの schema USAGE 権限をカタログ関数で観測する。"""
    with catalog.admin.cursor() as cursor:
        cursor.execute(
            "SELECT pg_catalog.has_schema_privilege(%s, %s, 'USAGE')",
            (role_id, schema_id),
        )
        row = cursor.fetchone()
    catalog.admin.rollback()
    if row is None or not isinstance(row[0], bool):
        raise AssertionError("schema USAGE権限を取得できない")
    return row[0]


def _grant_schema_usage_to_denied_controls(
    catalog: ProvisionedCatalog, contract: _ManagementContract
) -> None:
    """Schema 拒否を除外して対照ロールの関数 ACL だけを実行検査する。"""
    with catalog.admin.cursor() as cursor:
        for role_id in sorted(contract.denied_execute_role_ids):
            cursor.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(contract.schema_id),
                    sql.Identifier(role_id),
                )
            )
    catalog.admin.commit()


def _assert_management_schema_function_set(
    catalog: ProvisionedCatalog, contract: _ManagementContract
) -> None:
    """管理 schema の全関数を資産由来集合とカタログで exact-set 比較する。"""
    with catalog.admin.cursor() as cursor:
        cursor.execute(
            """
            SELECT routine.proname
            FROM pg_catalog.pg_proc AS routine
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = routine.pronamespace
            WHERE namespace.nspname = %s
              AND routine.prokind = 'f'
            ORDER BY routine.proname,
                     pg_catalog.pg_get_function_identity_arguments(routine.oid)
            """,
            (contract.schema_id,),
        )
        catalog_function_ids = tuple(str(row[0]) for row in cursor.fetchall())
    catalog.admin.rollback()
    if len(catalog_function_ids) != len(set(catalog_function_ids)):
        raise AssertionError("管理schemaに同名関数のoverloadがある")
    _assert_same_identifier_set(
        frozenset(catalog_function_ids),
        frozenset(contract.management_schema_function_ids),
        "管理schemaのカタログ関数と資産関数",
    )


_DDL_ASSET = _read_json_object(_DDL_ELEMENTS_PATH)
_MANAGEMENT_CONTRACT = _management_contract(_DDL_ASSET)


def test_management_function_path_and_catalog_scope(
    provisioned_catalog: ProvisionedCatalog,
    table_owner_connection: psycopg.Connection[Any],
    app_role_connection: psycopg.Connection[Any],
    management_caller_connection: psycopg.Connection[Any],
    outsider_role_connection: psycopg.Connection[Any],
) -> None:
    """資産由来の唯一の実行ロールだけが関数経由で副作用を作れる。"""
    _assert_failure_case_contract()
    contract = _management_contract(provisioned_catalog.asset)
    assert contract == _MANAGEMENT_CONTRACT

    role_connections = (
        table_owner_connection,
        app_role_connection,
        management_caller_connection,
        outsider_role_connection,
    )
    actual_login_role_ids = frozenset(
        _connection_role(connection) for connection in role_connections
    )
    _assert_same_identifier_set(
        actual_login_role_ids,
        frozenset(_authz_login_role_ids()),
        "4ロール実接続と資産由来LOGINロール",
    )
    assert _connection_role(management_caller_connection) == contract.calling_role_id
    _assert_management_schema_function_set(provisioned_catalog, contract)

    function_oid = _management_function_oid(provisioned_catalog, contract)
    assert _has_function_execute(
        provisioned_catalog, contract.calling_role_id, function_oid
    )

    _insert_management_fixture(provisioned_catalog, _BASELINE_FIXTURE)
    before_success = _effect_count(provisioned_catalog, contract)
    success_rows = _invoke_management_function(
        management_caller_connection,
        contract,
        _BASELINE_FIXTURE,
    )
    management_caller_connection.commit()
    after_success = _effect_count(provisioned_catalog, contract)
    expected_success_rows = (
        (
            True,
            _BASELINE_FIXTURE.invocation_group_id,
            _BASELINE_FIXTURE.invocation_target_tenant_id,
            _BASELINE_FIXTURE.invocation_effect_kind,
        ),
    )
    assert success_rows == expected_success_rows
    assert after_success == before_success + len(expected_success_rows)

    denied_connections = {
        _connection_role(connection): connection
        for connection in (app_role_connection, outsider_role_connection)
    }
    _assert_same_identifier_set(
        frozenset(denied_connections),
        contract.denied_execute_role_ids,
        "実行拒否の対照接続と資産由来ロール",
    )
    for role_id in denied_connections:
        assert not _has_schema_usage(provisioned_catalog, role_id, contract.schema_id)
        assert not _has_function_execute(provisioned_catalog, role_id, function_oid)

    _grant_schema_usage_to_denied_controls(provisioned_catalog, contract)
    for role_id, connection in denied_connections.items():
        assert _has_schema_usage(provisioned_catalog, role_id, contract.schema_id)
        before_denied_call = _effect_count(provisioned_catalog, contract)
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as error:
            _invoke_management_function(connection, contract, _BASELINE_FIXTURE)
        connection.rollback()
        after_denied_call = _effect_count(provisioned_catalog, contract)
        assert after_denied_call == before_denied_call
        assert error.value.diag.message_primary == (
            f"permission denied for function {contract.function_id}"
        )


@pytest.mark.parametrize(
    "case",
    _AUTHORIZATION_FAILURE_CASES,
    ids=tuple(case.decision_id for case in _AUTHORIZATION_FAILURE_CASES),
)
def test_each_management_authorization_failure_has_no_side_effect(
    provisioned_catalog: ProvisionedCatalog,
    management_caller_connection: psycopg.Connection[Any],
    case: _AuthorizationFailureCase,
) -> None:
    """各 DECISION 条件の単独失敗で副作用表の行数を不変に保つ。"""
    _assert_failure_case_contract()
    contract = _management_contract(provisioned_catalog.asset)
    assert contract == _MANAGEMENT_CONTRACT
    assert _connection_role(management_caller_connection) == contract.calling_role_id

    fixture = case.mutate(_BASELINE_FIXTURE)
    _insert_management_fixture(provisioned_catalog, fixture)
    before_call = _effect_count(provisioned_catalog, contract)
    returned_rows = _invoke_management_function(
        management_caller_connection,
        contract,
        fixture,
    )
    management_caller_connection.commit()
    after_call = _effect_count(provisioned_catalog, contract)

    assert after_call == before_call, case.decision_id
    assert returned_rows == (), case.decision_id
