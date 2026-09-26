"""製品認可 DDL を外部の superuser から一括適用・取り外しする。"""

from __future__ import annotations

import json
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


@dataclass(frozen=True, slots=True)
class _ProductElement:
    """製品資産の構造化された 1 要素を保持する。"""

    element_type: str
    element_id: str
    fields: dict[str, object]


def apply_product_authz_ddl(connection: psycopg.Connection[Any]) -> None:
    """製品認可 DDL を正規資産の固定順序で適用する。"""
    _run_product_operation(connection, ProductOperation.APPLY)


def unapply_product_authz_ddl(connection: psycopg.Connection[Any]) -> None:
    """製品認可 DDL を依存関係の逆順で取り外す。"""
    _run_product_operation(connection, ProductOperation.UNAPPLY)


def _load_product_elements() -> tuple[_ProductElement, ...]:
    """正規の staged 資産から構造化された全要素を読む。"""
    asset_path = _REPOSITORY_ROOT / PRODUCT_SPEC.ddl_elements_path
    try:
        with open(asset_path, encoding="utf-8") as asset_file:
            asset = json.load(asset_file)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProductProvisioningError(f"製品認可資産を読めない: {error}") from error
    if not isinstance(asset, dict):
        raise ProductProvisioningError("製品認可資産は JSON object が必要")

    elements: list[_ProductElement] = []
    for section in PRODUCT_SPEC.element_sections:
        rows = asset[section.section_name] if section.section_name in asset else None
        if not isinstance(rows, list) or not rows:
            raise ProductProvisioningError(
                f"製品認可資産の {section.section_name} は空でない配列が必要"
            )
        for index in range(len(rows)):
            row = rows[index]
            if not isinstance(row, dict):
                raise ProductProvisioningError(
                    f"製品認可資産の {section.section_name}[{index}] は object が必要"
                )
            element_id = row[section.id_field] if section.id_field in row else None
            if not isinstance(element_id, str) or not element_id:
                raise ProductProvisioningError(
                    f"製品認可資産の {section.section_name}[{index}]."
                    f"{section.id_field} は空でない文字列が必要"
                )
            if any(
                element.element_type == section.element_type
                and element.element_id == element_id
                for element in elements
            ):
                raise ProductProvisioningError(
                    f"製品認可資産の要素が重複している: "
                    f"{section.element_type}:{element_id}"
                )
            elements.append(
                _ProductElement(
                    element_type=section.element_type,
                    element_id=element_id,
                    fields=row,
                )
            )
    return tuple(elements)


def _element_for_statement(
    statement: DDLStatement,
    elements: tuple[_ProductElement, ...],
) -> _ProductElement:
    """生成文に対応する構造化資産要素を一意に返す。"""
    matches = tuple(
        element
        for element in elements
        if element.element_type == statement.element_type
        and element.element_id == statement.element_id
    )
    if len(matches) != 1:
        raise ProductProvisioningError(
            f"生成文の構造化資産要素を一意に取得できない: "
            f"{statement.element_type}:{statement.element_id}"
        )
    return matches[0]


def _element_text(element: _ProductElement, field_name: str) -> str:
    """構造化資産要素から空でない文字列を返す。"""
    value = element.fields[field_name] if field_name in element.fields else None
    if not isinstance(value, str) or not value:
        raise ProductProvisioningError(
            f"製品認可資産の {element.element_type}:{element.element_id}."
            f"{field_name} は空でない文字列が必要"
        )
    return value


def _element_string(element: _ProductElement, field_name: str) -> str:
    """構造化資産要素から空文字も許す文字列を返す。"""
    value = element.fields[field_name] if field_name in element.fields else None
    if not isinstance(value, str):
        raise ProductProvisioningError(
            f"製品認可資産の {element.element_type}:{element.element_id}."
            f"{field_name} は文字列が必要"
        )
    return value


def _quote_identifier(identifier: str) -> str:
    """PostgreSQL の識別子を常に二重引用符で安全に引用する。"""
    if not identifier or "\x00" in identifier:
        raise ProductProvisioningError("SQL 識別子は空または NUL を含められない")
    quoted = '"'
    for character in identifier:
        quoted += '""' if character == '"' else character
    return f'{quoted}"'


def _qualified_identifier(schema_name: str, object_name: str) -> str:
    """Schema と object の識別子を完全修飾して引用する。"""
    return f"{_quote_identifier(schema_name)}.{_quote_identifier(object_name)}"


def _identifier_list(identifiers: tuple[str, ...]) -> str:
    """空でない識別子列を引用済みのカンマ区切りへ変換する。"""
    if not identifiers:
        raise ProductProvisioningError("SQL 識別子列は空にできない")
    rendered = ""
    for identifier in identifiers:
        separator = ", " if rendered else ""
        rendered = f"{rendered}{separator}{_quote_identifier(identifier)}"
    return rendered


def _created_role_ids(elements: tuple[_ProductElement, ...]) -> tuple[str, ...]:
    """製品 DDL が作成して取り外すロール ID を資産順に返す。"""
    return tuple(
        _element_text(element, "role_id")
        for element in elements
        if element.element_type == "role"
        and _element_text(element, "creation") == "product_ddl"
    )


def _table_element(
    elements: tuple[_ProductElement, ...],
    table_id: str,
) -> _ProductElement:
    """表 ID に対応する構造化資産要素を一意に返す。"""
    matches = tuple(
        element
        for element in elements
        if element.element_type == "table"
        and _element_text(element, "table_id") == table_id
    )
    if len(matches) != 1:
        raise ProductProvisioningError(
            f"製品認可資産の表を一意に取得できない: {table_id}"
        )
    return matches[0]


def _element_group(statement: DDLStatement, element: _ProductElement) -> str:
    """生成文を適用手順資産の要素グループ名へ対応付ける。"""
    if statement.element_type == "role":
        return "roles"
    if statement.element_type == "database":
        return "databases"
    if statement.element_type == "schema":
        return "schemas"
    if statement.element_type == "function":
        return f"functions:{_element_text(element, 'function_kind')}"
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
    element: _ProductElement,
) -> int:
    """検証済みの適用手順資産から生成文の手順番号を得る。"""
    element_group = _element_group(statement, element)
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
    elements: tuple[_ProductElement, ...],
) -> tuple[_ProductStatement, ...]:
    """生成文を補助関数がポリシーより先になる順序へ並べる。"""
    statements: list[_ProductStatement] = []
    for statement in generated:
        element = _element_for_statement(statement, elements)
        if statement.element_type == "predicate":
            continue
        sequence = _application_sequence(statement, steps, element)
        sql_text = statement.sql
        if statement.element_type == "policy":
            table = _table_element(
                elements,
                _element_text(element, "table_id"),
            )
            qualified_table = _qualified_identifier(
                _element_text(table, "schema_name"),
                _element_text(table, "table_id"),
            )
            policy_name = _quote_identifier(
                f"pitchlog_app_{_element_text(element, 'profile')}"
            )
            sql_text = (
                f"DROP POLICY IF EXISTS {policy_name} ON {qualified_table};\n{sql_text}"
            )
        statements.append(_ProductStatement(sequence=sequence, sql=sql_text))
    return tuple(sorted(statements, key=lambda statement: statement.sequence))


def _database_unapplication_sql(product_role_ids: tuple[str, ...]) -> str:
    """現在の DB の ACL を migration 直後の形へ戻す文を返す。"""
    grantees = _identifier_list(product_role_ids)
    revoke_statement = f"REVOKE ALL PRIVILEGES ON DATABASE %I FROM {grantees}"
    return f"""
DO $authz$
DECLARE
    database_name TEXT;
BEGIN
    SELECT pg_catalog.current_database() INTO database_name;
    EXECUTE pg_catalog.format(
        $authz_statement${revoke_statement}$authz_statement$,
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
    element: _ProductElement,
    elements: tuple[_ProductElement, ...],
    preserved_role_ids: tuple[str, ...],
) -> str | None:
    """正規の適用要素から対応する取り外し文を導く。"""
    if statement.element_type == "role":
        role_id = _element_text(element, "role_id")
        if role_id in preserved_role_ids:
            return None
        return f"DROP ROLE IF EXISTS {_quote_identifier(role_id)};"
    if statement.element_type == "database":
        return _database_unapplication_sql(_created_role_ids(elements))
    if statement.element_type == "schema":
        schema_name = _element_text(element, "schema_name")
        quoted_schema = _quote_identifier(schema_name)
        creation = _element_text(element, "creation")
        if creation == "product_ddl":
            return f"DROP SCHEMA IF EXISTS {quoted_schema};"
        if creation == "existing":
            grantees = _identifier_list(_created_role_ids(elements))
            return f"""
REVOKE ALL PRIVILEGES ON SCHEMA {quoted_schema}
    FROM {grantees};
GRANT USAGE ON SCHEMA {quoted_schema} TO PUBLIC;
"""
    if statement.element_type == "function":
        qualified_function = _qualified_identifier(
            _element_text(element, "schema_name"),
            _element_text(element, "function_name"),
        )
        identity = f"{qualified_function}({_element_string(element, 'identity_args')})"
        if _element_text(element, "function_kind") == "rls_helper":
            return f"DROP FUNCTION IF EXISTS {identity};"
        return f"GRANT EXECUTE ON FUNCTION {identity} TO PUBLIC;"
    if statement.element_type == "table":
        table = _qualified_identifier(
            _element_text(element, "schema_name"),
            _element_text(element, "table_id"),
        )
        return f"""
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""
    if statement.element_type == "predicate":
        return None
    if statement.element_type == "policy":
        table = _table_element(elements, _element_text(element, "table_id"))
        policy_name = _quote_identifier(
            f"pitchlog_app_{_element_text(element, 'profile')}"
        )
        qualified_table = _qualified_identifier(
            _element_text(table, "schema_name"),
            _element_text(table, "table_id"),
        )
        return f"DROP POLICY IF EXISTS {policy_name} ON {qualified_table};"
    if statement.element_type == "acl_expectation":
        table = _qualified_identifier(
            _element_text(element, "object_schema"),
            _element_text(element, "object_id"),
        )
        grantee = _quote_identifier(_element_text(element, "grantee_role_id"))
        return f"REVOKE ALL PRIVILEGES ON TABLE {table} FROM {grantee};"
    if statement.element_type == "column_acl_expectation":
        table = _qualified_identifier(
            _element_text(element, "object_schema"),
            _element_text(element, "object_id"),
        )
        column = _quote_identifier(_element_text(element, "column_id"))
        grantee = _quote_identifier(_element_text(element, "grantee_role_id"))
        return f"REVOKE SELECT ({column}) ON TABLE {table} FROM {grantee};"
    raise ProductProvisioningError(
        f"製品認可の取り外し手順へ対応しない要素種別: {statement.element_type}"
    )


def _unapplication_statements(
    generated: tuple[DDLStatement, ...],
    steps: ProductApplicationSteps,
    elements: tuple[_ProductElement, ...],
) -> tuple[_ProductStatement, ...]:
    """生成文からポリシーを補助関数より先に落とす逆順を作る。"""
    statements: list[_ProductStatement] = []
    for statement in reversed(generated):
        element = _element_for_statement(statement, elements)
        application_sequence = _application_sequence(statement, steps, element)
        sql_text = _unapplication_sql(
            statement,
            element,
            elements,
            steps.preserved_role_ids,
        )
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
    elements = _load_product_elements()
    if operation is ProductOperation.APPLY:
        statements = _application_statements(generated, steps, elements)
    elif operation is ProductOperation.UNAPPLY:
        statements = _unapplication_statements(generated, steps, elements)
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
