"""管理呼び出しロールの直接表権限がないことを実 PostgreSQL で検証する。"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

import psycopg
import pytest
from psycopg import sql
from wording_scan import collect_wording_scan_files

from .conftest import ProvisionedCatalog, _role_id
from .test_authz_precondition_matrix import _assert_same_identifier_set, _only
from .test_authz_runtime_negative import _connection_role
from .test_authz_runtime_positive import (
    _object_rows,
    _read_json_object,
    _string,
    _string_tuple,
)

pytestmark = pytest.mark.requires_db

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DDL_ELEMENTS_PATH = _REPOSITORY_ROOT / "contracts/authz/ddl-elements.json"
_TARGET_TABLE_ID = "probe_management_effects"
_TEST_OWNER_PREFIX = "TSK-270.group2.table-privilege."
_EXECUTION_AND_CATALOG = "execution_and_catalog"
_CATALOG_ONLY = "catalog_only"

_VerificationMethod = Literal["execution_and_catalog", "catalog_only"]


@dataclass(frozen=True, slots=True)
class _TablePrivilegeCase:
    """資産の表権限 1 行と、その検証方式。"""

    privilege_id: str
    test_owner_id: str
    verification_method: _VerificationMethod
    catalog_only_reason: str | None


@dataclass(frozen=True, slots=True)
class _TablePrivilegeContract:
    """表権限行列とロール別 ACL の資産由来契約。"""

    cases: tuple[_TablePrivilegeCase, ...]
    calling_role_id: str
    app_role_id: str
    management_function_owner_id: str
    schema_id: str
    table_id: str
    column_ids: tuple[str, ...]
    app_role_privilege_ids: frozenset[str]
    management_function_owner_privilege_ids: frozenset[str]


_EXECUTION_PRIVILEGE_IDS: Final[frozenset[str]] = frozenset(
    {"SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"}
)
_CATALOG_ONLY_REASONS: Final[dict[str, str]] = {
    "REFERENCES": (
        "参照制約の作成には参照元表の作成権限と永続的な DDL 副作用も必要なため、"
        "has_table_privilege の false を直接の根拠とする"
    ),
    "TRIGGER": (
        "トリガー作成には実行関数と永続的な DDL 副作用も必要なため、"
        "has_table_privilege の false を直接の根拠とする"
    ),
    "MAINTAIN": (
        "保守文はトランザクション制約や運用上の副作用を伴うため、"
        "has_table_privilege の false を直接の根拠とする"
    ),
}

_WORDING_SCAN_ROOTS: Final[tuple[Path, ...]] = (
    Path("backend"),
    Path("scripts"),
    Path("contracts"),
    Path("tests"),
    Path("docs/features/pg-authz-verification-g2"),
)
_WORDING_SCAN_EXCLUSIONS: Final[frozenset[Path]] = frozenset(
    {Path("docs/features/pg-authz-verification-g2/plan.md")}
)


def _required_object(value: object, label: str) -> dict[str, object]:
    """資産値を JSON object として検証する。

    Args:
        value: 検証対象の資産値。
        label: エラーへ付ける資産位置。

    Returns:
        型検証済みの JSON object。
    """
    if not isinstance(value, dict):
        raise AssertionError(f"{label}はobjectでなければならない")
    return value


def _acl_privilege_ids(
    asset: dict[str, object], table_id: str, grantee_role_id: str
) -> frozenset[str]:
    """表と被付与ロールから ACL 権限集合を一意に得る。

    Args:
        asset: DDL 要素資産。
        table_id: 対象表 ID。
        grantee_role_id: 被付与ロール ID。

    Returns:
        ACL 行が宣言する表権限集合。
    """
    rows = tuple(
        row
        for row in _object_rows(asset.get("acl_expectations"), "acl_expectations")
        if row.get("object_kind") == "table"
        and row.get("object_id") == table_id
        and row.get("grantee_role_id") == grantee_role_id
    )
    row = _only(rows, f"{table_id}/{grantee_role_id} の表 ACL")
    privilege_ids = _string_tuple(
        row.get("privilege_ids"), f"{table_id}/{grantee_role_id}.privilege_ids"
    )
    return frozenset(privilege_ids)


def _management_function_owner_id(asset: dict[str, object]) -> str:
    """代表管理関数から関数所有ロール ID を導出する。

    Args:
        asset: DDL 要素資産。

    Returns:
        代表管理関数の所有ロール ID。
    """
    probe = _required_object(
        asset.get("representative_management_probe"),
        "representative_management_probe",
    )
    function_id = _string(probe.get("function_id"), "management function_id")
    function = _only(
        tuple(
            row
            for row in _object_rows(asset.get("functions"), "functions")
            if row.get("function_id") == function_id
        ),
        f"代表管理関数 {function_id}",
    )
    owner_role_id = _string(
        function.get("owner_role_id"), f"{function_id}.owner_role_id"
    )
    owner_role = _only(
        tuple(
            row
            for row in _object_rows(asset.get("roles"), "roles")
            if row.get("role_id") == owner_role_id
        ),
        f"代表管理関数所有ロール {owner_role_id}",
    )
    if owner_role.get("role_kind") != "function_owner" or owner_role.get("login"):
        raise AssertionError("代表管理関数の所有者が NOLOGIN の function_owner でない")
    return owner_role_id


def _verification_method(privilege_id: str) -> tuple[_VerificationMethod, str | None]:
    """権限 ID に対応する検証方式とカタログ限定理由を返す。

    Args:
        privilege_id: enum から導出した表権限 ID。

    Returns:
        検証方式と、カタログ限定時だけ存在する理由。
    """
    if privilege_id in _EXECUTION_PRIVILEGE_IDS:
        return _EXECUTION_AND_CATALOG, None
    try:
        reason = _CATALOG_ONLY_REASONS[privilege_id]
    except KeyError as error:
        raise AssertionError(
            f"表権限の検証方式が閉じていない: {privilege_id}"
        ) from error
    return _CATALOG_ONLY, reason


def _table_privilege_contract(
    asset: dict[str, object],
) -> _TablePrivilegeContract:
    """Enum を母集合として表権限行列と ACL 契約を組み立てる。

    Args:
        asset: DDL 要素資産。

    Returns:
        enum 順の検証ケースとロール別 ACL 契約。
    """
    enums = _required_object(asset.get("enums"), "enums")
    privilege_ids = _string_tuple(
        enums.get("table_privilege_ids"), "enums.table_privilege_ids"
    )
    privilege_id_set = frozenset(privilege_ids)
    if not privilege_ids:
        raise AssertionError("enums.table_privilege_idsが空である")

    rows = _object_rows(
        asset.get("table_privilege_probe_matrix"), "table_privilege_probe_matrix"
    )
    matrix_privilege_ids = tuple(
        _string(row.get("privilege_id"), "matrix.privilege_id") for row in rows
    )
    if len(matrix_privilege_ids) != len(set(matrix_privilege_ids)):
        raise AssertionError("table_privilege_probe_matrixのprivilege_idが重複している")
    _assert_same_identifier_set(
        frozenset(matrix_privilege_ids),
        privilege_id_set,
        "表権限 enum と table_privilege_probe_matrix.privilege_id",
    )

    calling_role_id = _role_id(asset, "management_caller")
    app_role_id = _role_id(asset, "tested_caller")
    tables = _object_rows(asset.get("tables"), "tables")
    table = _only(
        tuple(row for row in tables if row.get("table_id") == _TARGET_TABLE_ID),
        f"対象表 {_TARGET_TABLE_ID}",
    )
    if table.get("force_rls") is not True:
        raise AssertionError(f"{_TARGET_TABLE_ID}にFORCE ROW LEVEL SECURITYがない")
    schema_id = _string(table.get("schema_id"), f"{_TARGET_TABLE_ID}.schema_id")
    column_ids = _string_tuple(
        table.get("row_shape_ids"), f"{_TARGET_TABLE_ID}.row_shape_ids"
    )

    row_by_privilege_id = {
        _string(row.get("privilege_id"), "matrix.privilege_id"): row for row in rows
    }
    cases: list[_TablePrivilegeCase] = []
    test_owner_ids: set[str] = set()
    for privilege_id in privilege_ids:
        row = row_by_privilege_id[privilege_id]
        if (
            row.get("calling_role_id") != calling_role_id
            or row.get("target_table_id") != _TARGET_TABLE_ID
            or row.get("expected_direct_access") != "deny"
        ):
            raise AssertionError(f"表権限行列の拒否契約が不正: {privilege_id}")
        test_owner = _required_object(
            row.get("test_owner"), f"{privilege_id}.test_owner"
        )
        test_owner_id = _string(test_owner.get("id"), f"{privilege_id}.test_owner.id")
        expected_test_owner_id = f"{_TEST_OWNER_PREFIX}{privilege_id.lower()}"
        if test_owner_id != expected_test_owner_id:
            raise AssertionError(f"権限とtest_owner.idの対応が不正: {privilege_id}")
        if test_owner.get("status") != "planned":
            raise AssertionError(
                f"表権限test_owner.statusがplannedでない: {privilege_id}"
            )
        verification_method, reason = _verification_method(privilege_id)
        cases.append(
            _TablePrivilegeCase(
                privilege_id=privilege_id,
                test_owner_id=test_owner_id,
                verification_method=verification_method,
                catalog_only_reason=reason,
            )
        )
        test_owner_ids.add(test_owner_id)

    expected_test_owner_ids = frozenset(
        f"{_TEST_OWNER_PREFIX}{privilege_id.lower()}" for privilege_id in privilege_ids
    )
    _assert_same_identifier_set(
        frozenset(test_owner_ids),
        expected_test_owner_ids,
        "table_privilege_probe_matrix.test_owner.id",
    )

    management_function_owner_id = _management_function_owner_id(asset)
    app_role_privilege_ids = _acl_privilege_ids(asset, _TARGET_TABLE_ID, app_role_id)
    management_function_owner_privilege_ids = _acl_privilege_ids(
        asset, _TARGET_TABLE_ID, management_function_owner_id
    )
    if not app_role_privilege_ids:
        raise AssertionError("app_role の対照用表権限が空である")
    if management_function_owner_privilege_ids != frozenset({"INSERT"}):
        raise AssertionError("代表管理関数所有ロールの表権限がINSERTだけでない")
    caller_acl_rows = tuple(
        row
        for row in _object_rows(asset.get("acl_expectations"), "acl_expectations")
        if row.get("object_kind") == "table"
        and row.get("object_id") == _TARGET_TABLE_ID
        and row.get("grantee_role_id") == calling_role_id
    )
    if caller_acl_rows:
        raise AssertionError("管理呼び出しロールに対象表 ACL が宣言されている")

    return _TablePrivilegeContract(
        cases=tuple(cases),
        calling_role_id=calling_role_id,
        app_role_id=app_role_id,
        management_function_owner_id=management_function_owner_id,
        schema_id=schema_id,
        table_id=_TARGET_TABLE_ID,
        column_ids=column_ids,
        app_role_privilege_ids=app_role_privilege_ids,
        management_function_owner_privilege_ids=(
            management_function_owner_privilege_ids
        ),
    )


def _has_table_privilege(
    connection: psycopg.Connection[Any],
    role_id: str,
    contract: _TablePrivilegeContract,
    privilege_id: str,
) -> bool:
    """指定ロールの表権限を PostgreSQL カタログ関数で観測する。

    Args:
        connection: カタログ関数を呼ぶ管理接続。
        role_id: 観測対象ロール ID。
        contract: 対象 schema と表を持つ資産由来契約。
        privilege_id: 観測対象の表権限 ID。

    Returns:
        ``has_table_privilege`` の真偽値。
    """
    qualified_table = f"{contract.schema_id}.{contract.table_id}"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_catalog.has_table_privilege(%s, %s, %s)",
            (role_id, qualified_table, privilege_id),
        )
        row = cursor.fetchone()
    connection.rollback()
    if row is None or not isinstance(row[0], bool):
        raise AssertionError("has_table_privilegeが真偽値を返さなかった")
    return row[0]


def _grant_schema_usage_for_table_probe(
    catalog: ProvisionedCatalog, contract: _TablePrivilegeContract
) -> None:
    """Schema 拒否を除外して表権限だけを実操作で検証可能にする。

    Args:
        catalog: 適用済みの使い捨て構成。
        contract: 呼び出しロールと対象 schema を持つ契約。
    """
    with catalog.admin.cursor() as cursor:
        cursor.execute(
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                sql.Identifier(contract.schema_id),
                sql.Identifier(contract.calling_role_id),
            )
        )
    catalog.admin.commit()

    with catalog.admin.cursor() as cursor:
        cursor.execute(
            "SELECT pg_catalog.has_schema_privilege(%s, %s, 'USAGE')",
            (contract.calling_role_id, contract.schema_id),
        )
        row = cursor.fetchone()
    catalog.admin.rollback()
    assert row == (True,), "実操作の前提となるschema USAGEを付与できていない"


def _direct_operation(
    case: _TablePrivilegeCase, contract: _TablePrivilegeContract
) -> tuple[sql.Composed, tuple[object, ...]]:
    """実行確認対象の権限から実 SQL とパラメータを組み立てる。

    Args:
        case: enum 由来の表権限ケース。
        contract: 対象 relation と列を持つ資産由来契約。

    Returns:
        psycopg へ渡す SQL とパラメータ。
    """
    relation = sql.Identifier(contract.schema_id, contract.table_id)
    if case.privilege_id == "SELECT":
        return sql.SQL("SELECT * FROM {}").format(relation), ()
    if case.privilege_id == "INSERT":
        columns = sql.SQL(", ").join(
            sql.Identifier(column_id) for column_id in contract.column_ids
        )
        placeholders = sql.SQL(", ").join(
            sql.Placeholder() for _column_id in contract.column_ids
        )
        values = tuple(
            index if column_id.endswith("_id") else "direct-table-privilege-probe"
            for index, column_id in enumerate(contract.column_ids, start=1)
        )
        return (
            sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                relation, columns, placeholders
            ),
            values,
        )
    if case.privilege_id == "UPDATE":
        return (
            sql.SQL("UPDATE {} SET {} = %s").format(
                relation, sql.Identifier(contract.column_ids[-1])
            ),
            ("direct-table-privilege-probe",),
        )
    if case.privilege_id == "DELETE":
        return sql.SQL("DELETE FROM {}").format(relation), ()
    if case.privilege_id == "TRUNCATE":
        return sql.SQL("TRUNCATE TABLE {}").format(relation), ()
    raise AssertionError(f"実行確認対象でない表権限: {case.privilege_id}")


def _assert_direct_operation_is_table_privilege_denied(
    connection: psycopg.Connection[Any],
    case: _TablePrivilegeCase,
    contract: _TablePrivilegeContract,
) -> None:
    """実文が表権限エラーになることを要求する。

    成功して RLS により 0 行となる結果は合格にせず、例外クラスと表名を含む
    PostgreSQL の診断を要求する。

    Args:
        connection: 管理呼び出しロール自身で認証した接続。
        case: 実行確認する表権限ケース。
        contract: 対象 relation を持つ資産由来契約。
    """
    statement, parameters = _direct_operation(case, contract)
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as error:
            with connection.cursor() as cursor:
                cursor.execute(statement, parameters)
    finally:
        connection.rollback()
    assert error.value.diag.message_primary == (
        f"permission denied for table {contract.table_id}"
    )


_DDL_ASSET = _read_json_object(_DDL_ELEMENTS_PATH)
_TABLE_PRIVILEGE_CONTRACT = _table_privilege_contract(_DDL_ASSET)


def test_each_omitted_matrix_privilege_is_red() -> None:
    """資産の表権限行列からどの 1 行を除いても exact-set 不一致にする。"""
    for case in _TABLE_PRIVILEGE_CONTRACT.cases:
        mutated = copy.deepcopy(_DDL_ASSET)
        rows = _object_rows(
            mutated.get("table_privilege_probe_matrix"),
            "table_privilege_probe_matrix",
        )
        mutated["table_privilege_probe_matrix"] = [
            row for row in rows if row.get("privilege_id") != case.privilege_id
        ]
        with pytest.raises(AssertionError, match="exact-set"):
            _table_privilege_contract(mutated)


def test_current_step_has_no_legacy_privilege_count_wording() -> None:
    """指定された成果物範囲に旧来の権限件数表現を残さない。"""
    forbidden = ("6" + " 権限").encode()
    violations = tuple(
        item.path
        for item in collect_wording_scan_files(
            _REPOSITORY_ROOT,
            _WORDING_SCAN_ROOTS,
            _WORDING_SCAN_EXCLUSIONS,
        )
        if forbidden in item.content
    )
    assert violations == ()


@pytest.mark.parametrize(
    "case",
    _TABLE_PRIVILEGE_CONTRACT.cases,
    ids=tuple(case.test_owner_id for case in _TABLE_PRIVILEGE_CONTRACT.cases),
)
def test_management_caller_table_privilege_is_absent_and_denied(
    case: _TablePrivilegeCase,
    provisioned_catalog: ProvisionedCatalog,
    app_role_connection: psycopg.Connection[Any],
    management_caller_connection: psycopg.Connection[Any],
) -> None:
    """全 enum 権限をカタログ確認し、実行可能な操作は実拒否も確認する。"""
    contract = _table_privilege_contract(provisioned_catalog.asset)
    assert contract == _TABLE_PRIVILEGE_CONTRACT
    assert _connection_role(management_caller_connection) == contract.calling_role_id
    assert _connection_role(app_role_connection) == contract.app_role_id

    caller_has_privilege = _has_table_privilege(
        provisioned_catalog.admin,
        contract.calling_role_id,
        contract,
        case.privilege_id,
    )
    app_role_has_privilege = _has_table_privilege(
        provisioned_catalog.admin,
        contract.app_role_id,
        contract,
        case.privilege_id,
    )
    function_owner_has_privilege = _has_table_privilege(
        provisioned_catalog.admin,
        contract.management_function_owner_id,
        contract,
        case.privilege_id,
    )

    assert caller_has_privilege is False
    assert app_role_has_privilege is (
        case.privilege_id in contract.app_role_privilege_ids
    )
    assert function_owner_has_privilege is (
        case.privilege_id in contract.management_function_owner_privilege_ids
    )

    if case.verification_method == _CATALOG_ONLY:
        assert case.catalog_only_reason is not None
        return

    assert case.verification_method == _EXECUTION_AND_CATALOG
    assert case.catalog_only_reason is None
    _grant_schema_usage_for_table_probe(provisioned_catalog, contract)
    _assert_direct_operation_is_table_privilege_denied(
        management_caller_connection, case, contract
    )
