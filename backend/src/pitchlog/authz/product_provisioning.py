"""製品認可 DDL を外部の superuser から一括適用・取り外しする。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import psycopg
from psycopg import pq

from pitchlog.authz.asset_spec import (
    PRODUCT_SPEC,
    ProductApplicationSteps,
    load_product_application_steps,
)
from pitchlog.authz.ddl import DDLStatement, generate_authz_ddl

_REPOSITORY_ROOT = Path(__file__).parents[4]
_HELPER_FUNCTION_ID = (
    "FUNCTION:authz_private:tenant_has_effective_membership(uuid, boolean)"
)
_IDENTITY_QUERY = """
SELECT current_user::text, session_user::text, role.rolsuper
FROM pg_catalog.pg_roles AS role
WHERE role.rolname = current_user
"""
_SUBJECT_CHANGE_PATTERN = re.compile(
    r"\b(?:SET\s+(?:(?:LOCAL|SESSION)\s+)?ROLE|RESET\s+ROLE|"
    r"SET\s+SESSION\s+AUTHORIZATION|RESET\s+SESSION\s+AUTHORIZATION)\b",
    re.IGNORECASE,
)


class ProductProvisioningError(RuntimeError):
    """製品認可 DDL を安全に適用または取り外しできないことを表す。"""


class ProductOperation(Enum):
    """製品認可の末端が受け付ける閉じた操作種別。"""

    APPLY = "apply"
    UNAPPLY = "unapply"


@dataclass(frozen=True, slots=True)
class _ProductStatement:
    """製品の 1 手順で実行する正規資産由来の文。"""

    sequence: int
    sql: str


def apply_product_authz_ddl(connection: psycopg.Connection[Any]) -> None:
    """製品認可 DDL を正規資産の固定順序で適用する。"""
    _run_product_operation(connection, ProductOperation.APPLY)


def unapply_product_authz_ddl(connection: psycopg.Connection[Any]) -> None:
    """製品認可 DDL を依存関係の逆順で取り外す。"""
    _run_product_operation(connection, ProductOperation.UNAPPLY)


def _element_group(statement: DDLStatement) -> str:
    """生成文を適用手順資産の要素グループ名へ対応付ける。"""
    if statement.element_type == "role":
        return "roles"
    if statement.element_type == "database":
        return "databases"
    if statement.element_type == "schema":
        return "schemas"
    if statement.element_type == "function":
        return (
            "functions:rls_helper"
            if statement.element_id == _HELPER_FUNCTION_ID
            else "functions:migration_trigger"
        )
    if statement.element_type == "table":
        return "tables"
    if statement.element_type == "predicate":
        return "predicates"
    if statement.element_type == "policy":
        return "policies"
    if statement.element_type == "acl_expectation":
        return "acl_expectations"
    if statement.element_type == "column_acl_expectation":
        return "column_acl_expectations"
    raise ProductProvisioningError(
        f"製品認可の適用手順へ対応しない要素種別: {statement.element_type}"
    )


def _application_sequence(
    statement: DDLStatement,
    steps: ProductApplicationSteps,
) -> int:
    """検証済みの適用手順資産から生成文の手順番号を得る。"""
    element_group = _element_group(statement)
    matches = tuple(
        step.sequence
        for step in steps.application_steps
        if element_group in step.element_groups
    )
    if len(matches) != 1:
        raise ProductProvisioningError(
            f"製品認可の要素グループを一意な手順へ対応できない: {element_group}"
        )
    return matches[0]


def _application_statements(
    generated: tuple[DDLStatement, ...],
    steps: ProductApplicationSteps,
) -> tuple[_ProductStatement, ...]:
    """生成文を補助関数がポリシーより先になる順序へ並べる。"""
    statements: list[_ProductStatement] = []
    for statement in generated:
        if statement.element_type == "predicate":
            continue
        sequence = _application_sequence(statement, steps)
        sql_text = statement.sql
        if statement.element_type == "policy":
            parts = statement.element_id.split(":", maxsplit=2)
            if len(parts) != 3:
                raise ProductProvisioningError(
                    f"製品認可ポリシーの要素 ID が不正: {statement.element_id}"
                )
            sql_text = (
                f"DROP POLICY IF EXISTS pitchlog_app_{parts[2]} "
                f"ON public.{parts[1]};\n{sql_text}"
            )
        statements.append(_ProductStatement(sequence=sequence, sql=sql_text))
    return tuple(sorted(statements, key=lambda statement: statement.sequence))


def _database_unapplication_sql() -> str:
    """現在の DB の ACL を migration 直後の形へ戻す文を返す。"""
    return """
DO $authz$
DECLARE
    database_name TEXT := pg_catalog.current_database();
BEGIN
    EXECUTE pg_catalog.format(
        'REVOKE ALL PRIVILEGES ON DATABASE %I FROM pitchlog_app, '
        'pitchlog_shared_fn_owner, pitchlog_management_fn_owner',
        database_name
    );
    EXECUTE pg_catalog.format(
        'GRANT CONNECT, TEMPORARY ON DATABASE %I TO PUBLIC',
        database_name
    );
END;
$authz$;
"""


def _unapplication_sql(
    statement: DDLStatement,
    preserved_role_ids: tuple[str, ...],
) -> str | None:
    """正規の適用要素から対応する取り外し文を導く。"""
    if statement.element_type == "role":
        if statement.element_id in preserved_role_ids:
            return None
        return f"DROP ROLE IF EXISTS {statement.element_id};"
    if statement.element_type == "database":
        return _database_unapplication_sql()
    if statement.element_type == "schema":
        if statement.element_id == "authz_private":
            return "DROP SCHEMA IF EXISTS authz_private;"
        if statement.element_id == "public":
            return """
REVOKE ALL PRIVILEGES ON SCHEMA public
    FROM pitchlog_app, pitchlog_shared_fn_owner, pitchlog_management_fn_owner;
GRANT USAGE ON SCHEMA public TO PUBLIC;
"""
    if statement.element_type == "function":
        identity = statement.element_id[len("FUNCTION:") :]
        if statement.element_id == _HELPER_FUNCTION_ID:
            return f"DROP FUNCTION IF EXISTS {identity};"
        return f"GRANT EXECUTE ON FUNCTION {identity} TO PUBLIC;"
    if statement.element_type == "table":
        return f"""
ALTER TABLE public.{statement.element_id} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public.{statement.element_id} DISABLE ROW LEVEL SECURITY;
"""
    if statement.element_type == "predicate":
        return None
    if statement.element_type == "policy":
        parts = statement.element_id.split(":", maxsplit=2)
        if len(parts) != 3:
            raise ProductProvisioningError(
                f"製品認可ポリシーの要素 ID が不正: {statement.element_id}"
            )
        return f"DROP POLICY IF EXISTS pitchlog_app_{parts[2]} ON public.{parts[1]};"
    if statement.element_type == "acl_expectation":
        parts = statement.element_id.split(":", maxsplit=2)
        if len(parts) != 3:
            raise ProductProvisioningError(
                f"製品認可 ACL の要素 ID が不正: {statement.element_id}"
            )
        return f"REVOKE ALL PRIVILEGES ON TABLE public.{parts[1]} FROM {parts[2]};"
    if statement.element_type == "column_acl_expectation":
        parts = statement.element_id.split(":", maxsplit=4)
        if len(parts) != 5:
            raise ProductProvisioningError(
                f"製品認可列 ACL の要素 ID が不正: {statement.element_id}"
            )
        return (
            f"REVOKE SELECT ({parts[3]}) ON TABLE {parts[1]}.{parts[2]} "
            f"FROM {parts[4]};"
        )
    raise ProductProvisioningError(
        f"製品認可の取り外し手順へ対応しない要素種別: {statement.element_type}"
    )


def _unapplication_statements(
    generated: tuple[DDLStatement, ...],
    steps: ProductApplicationSteps,
) -> tuple[_ProductStatement, ...]:
    """生成文からポリシーを補助関数より先に落とす逆順を作る。"""
    statements: list[_ProductStatement] = []
    for statement in reversed(generated):
        application_sequence = _application_sequence(statement, steps)
        sql_text = _unapplication_sql(statement, steps.preserved_role_ids)
        if sql_text is not None:
            statements.append(
                _ProductStatement(sequence=8 - application_sequence, sql=sql_text)
            )
    return tuple(sorted(statements, key=lambda statement: statement.sequence))


def _build_operation_statements(
    operation: ProductOperation,
) -> tuple[ProductApplicationSteps, tuple[_ProductStatement, ...]]:
    """正規の置き場だけから手順と実行文を生成する。"""
    steps = load_product_application_steps(_REPOSITORY_ROOT, PRODUCT_SPEC)
    generated = generate_authz_ddl(_REPOSITORY_ROOT, PRODUCT_SPEC)
    if operation is ProductOperation.APPLY:
        statements = _application_statements(generated, steps)
    elif operation is ProductOperation.UNAPPLY:
        statements = _unapplication_statements(generated, steps)
    else:  # pragma: no cover - Enum の閉包を型検査にも明示する。
        raise ProductProvisioningError(f"未定義の製品認可操作: {operation!r}")
    if {statement.sequence for statement in statements} != set(range(1, 8)):
        raise ProductProvisioningError("製品認可の実行文が固定の 7 手順を覆っていない")
    return steps, statements


def _assert_no_subject_change(statements: tuple[_ProductStatement, ...]) -> None:
    """生成文にセッション主体を変える文が含まれないことを保証する。"""
    for statement in statements:
        if _SUBJECT_CHANGE_PATTERN.search(statement.sql) is not None:
            raise ProductProvisioningError(
                f"製品認可の生成文が適用主体を変更する: 手順 {statement.sequence}"
            )


def _assert_identity_row(
    row: tuple[object, ...] | None,
    checkpoint_id: str,
    *,
    require_superuser: bool,
) -> None:
    """記録点の現在主体と認証主体、および必要な権限を検査する。"""
    if row is None or len(row) != 3:
        raise ProductProvisioningError(
            f"適用主体の識別結果が一意でない: {checkpoint_id}"
        )
    current_user, session_user, is_superuser = row
    if current_user != session_user:
        raise ProductProvisioningError(
            f"current_user と session_user が一致しない: {checkpoint_id}"
        )
    if current_user == "pitchlog_app":
        raise ProductProvisioningError("pitchlog_app は製品認可を適用できない")
    if require_superuser and is_superuser is not True:
        raise ProductProvisioningError(
            "製品認可の適用主体は superuser でなければならない"
        )


def _checkpoint_id(
    operation: ProductOperation,
    sequence: int,
    statement_number: int,
    statement_count: int,
) -> str | None:
    """設計で固定した故障注入用の記録点 ID を返す。"""
    is_last = statement_number == statement_count
    if operation is ProductOperation.APPLY:
        if sequence in {1, 4} and is_last:
            return f"product:{sequence}:after"
        if sequence == 3 and is_last:
            return "product:3:after_helper_function_creation"
        if sequence == 5 and is_last:
            return "product:5:after_policy_creation"
        if sequence == 6 and statement_number == 1:
            return "product:6:during"
        return None
    if sequence == 3 and is_last:
        return "product:3:after_policy_drop"
    if sequence == 5 and is_last:
        return "product:5:after_helper_function_drop"
    return None


def _record_product_checkpoint(checkpoint_id: str) -> None:
    """故障注入試験が差し替える製品適用器の記録点。"""
    del checkpoint_id


def _run_product_operation(
    connection: psycopg.Connection[Any],
    operation: ProductOperation,
) -> None:
    """閉じた操作を正規資産から生成し、1 トランザクションで実行する。"""
    if connection.closed:
        raise ProductProvisioningError("閉じた接続では製品認可を操作できない")
    if connection.autocommit:
        raise ProductProvisioningError("autocommit 接続では製品認可を操作できない")
    if connection.info.transaction_status is not pq.TransactionStatus.IDLE:
        raise ProductProvisioningError(
            "進行中のトランザクションがある接続では製品認可を操作できない"
        )

    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute(_IDENTITY_QUERY)
            identity_row: tuple[object, ...] | None = None
            for row in cursor:
                if identity_row is not None:
                    raise ProductProvisioningError("適用主体の識別結果が複数ある")
                identity_row = row
        _assert_identity_row(
            identity_row,
            "product:0:precondition",
            require_superuser=True,
        )
    finally:
        connection.autocommit = False

    steps, statements = _build_operation_statements(operation)
    if steps.transaction != "single":
        raise ProductProvisioningError("製品認可の transaction は single が必要")
    _assert_no_subject_change(statements)

    transaction_started = False
    current_sequence = 1
    try:
        with connection.cursor() as cursor:
            for sequence in range(1, 8):
                current_sequence = sequence
                step_statements = tuple(
                    statement
                    for statement in statements
                    if statement.sequence == sequence
                )
                statement_number = 0
                for statement in step_statements:
                    transaction_started = True
                    cursor.execute(statement.sql.encode("utf-8"))
                    statement_number += 1
                    checkpoint_id = _checkpoint_id(
                        operation,
                        sequence,
                        statement_number,
                        len(step_statements),
                    )
                    if checkpoint_id is not None:
                        cursor.execute(_IDENTITY_QUERY)
                        checkpoint_row: tuple[object, ...] | None = None
                        for row in cursor:
                            if checkpoint_row is not None:
                                raise ProductProvisioningError(
                                    f"記録点の識別結果が複数ある: {checkpoint_id}"
                                )
                            checkpoint_row = row
                        _assert_identity_row(
                            checkpoint_row,
                            checkpoint_id,
                            require_superuser=True,
                        )
                        _record_product_checkpoint(checkpoint_id)
        connection.commit()
    except Exception:
        if transaction_started:
            connection.rollback()
            connection.autocommit = True
            try:
                with connection.cursor() as cursor:
                    cursor.execute(_IDENTITY_QUERY)
                    rollback_row: tuple[object, ...] | None = None
                    for row in cursor:
                        if rollback_row is not None:
                            raise ProductProvisioningError(
                                "rollback 後の識別結果が複数ある"
                            )
                        rollback_row = row
                rollback_checkpoint = f"product:{current_sequence}:after_rollback"
                _assert_identity_row(
                    rollback_row,
                    rollback_checkpoint,
                    require_superuser=True,
                )
                _record_product_checkpoint(rollback_checkpoint)
            finally:
                connection.autocommit = False
        raise

    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute(_IDENTITY_QUERY)
            commit_row: tuple[object, ...] | None = None
            for row in cursor:
                if commit_row is not None:
                    raise ProductProvisioningError("commit 後の識別結果が複数ある")
                commit_row = row
        commit_checkpoint = "product:7:after_commit"
        _assert_identity_row(
            commit_row,
            commit_checkpoint,
            require_superuser=True,
        )
        _record_product_checkpoint(commit_checkpoint)
    finally:
        connection.autocommit = False
