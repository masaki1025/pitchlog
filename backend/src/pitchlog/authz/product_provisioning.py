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
from pitchlog.authz.product_control_access import (
    INITIAL_STORAGE_TABLES,
    RULE_RESOLUTION_FUNCTION_ID,
    RULE_RESOLUTION_OWNER_ROLE_ID,
    is_enrollment_column_acl,
    is_initial_column_acl,
    is_rg1_control_column_acl,
    is_rg1_singleton_update_acl,
    is_rule_resolution_update_acl,
)

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
    APPLY_PRE_RULE = "apply_pre_rule"
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


def apply_product_authz_before_rule_placement(
    connection: psycopg.Connection[Any],
) -> None:
    """規則配置・epoch列追加前の依存権限だけを保留して認可を適用する。"""
    _run_product_operation(connection, ProductOperation.APPLY_PRE_RULE)


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
        if section.section_name == "extensions" and rows is None:
            continue
        if not isinstance(rows, list) or (
            not rows and section.section_name != "extensions"
        ):
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


def _policy_name(element: _ProductElement) -> str:
    """検査済み資産からポリシー名を取得する。"""
    if "policy_name" in element.fields:
        return _element_text(element, "policy_name")
    return f"pitchlog_app_{_element_text(element, 'profile')}"


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
    if statement.element_type == "extension":
        return "extensions"
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


def _ordered_generated_statements(
    generated: tuple[DDLStatement, ...],
    steps: ProductApplicationSteps,
    elements: tuple[_ProductElement, ...],
) -> tuple[DDLStatement, ...]:
    """手順と要素群の宣言順で SQL 要素を並べる。"""
    ranked: list[tuple[int, int, int, DDLStatement]] = []
    for index, statement in enumerate(generated):
        element = _element_for_statement(statement, elements)
        sequence = _application_sequence(statement, steps, element)
        groups = steps.application_steps[sequence - 1].element_groups
        ranked.append(
            (
                sequence,
                groups.index(_element_group(statement, element)),
                index,
                statement,
            )
        )
    return tuple(row[3] for row in sorted(ranked))


def _strict_lifecycle_schema_sql(element: _ProductElement, sql_text: str) -> str:
    """新schema2だけを既存owner不修復の再適用ガードで包む。"""
    schema_name = _element_text(element, "schema_name")
    owner = _element_text(element, "owner")
    if (
        schema_name != _element_text(element, "schema_id")
        or schema_name
        not in {"rg1_control", "pitchlog_ledger_observer", "initial_right_api"}
        or _element_text(element, "creation") != "product_ddl"
        or _element_text(element, "ownership_path") != "direct"
    ):
        raise ProductProvisioningError("新schemaの再適用対象が閉集合と不一致")
    if (
        owner
        != {
            "rg1_control": "pitchlog_rg1_control_owner",
            "pitchlog_ledger_observer": "pitchlog_ledger_identity_owner",
            "initial_right_api": "pitchlog_initial_fn_owner",
        }[schema_name]
    ):
        raise ProductProvisioningError("新schemaのownerが閉集合と不一致")
    original_create = f"CREATE SCHEMA {schema_name} AUTHORIZATION {owner};"
    if sql_text.count(original_create) != 1:
        raise ProductProvisioningError("新schemaの正規CREATE文が一意でない")
    schema_literal = "'" + schema_name.replace("'", "''") + "'"
    owner_literal = "'" + owner.replace("'", "''") + "'"
    guarded_create = f"""DO $schema_reapply$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = {schema_literal}
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_namespace n
            JOIN pg_catalog.pg_roles r ON r.oid = n.nspowner
            WHERE n.nspname = {schema_literal} AND r.rolname = {owner_literal}
        ) THEN
            RAISE EXCEPTION 'schema owner collision: {schema_name}';
        END IF;
    ELSE
        CREATE SCHEMA {_quote_identifier(schema_name)}
            AUTHORIZATION {_quote_identifier(owner)};
    END IF;
END;
$schema_reapply$;"""
    return sql_text.replace(original_create, guarded_create, 1)


def _application_statements(
    generated: tuple[DDLStatement, ...],
    steps: ProductApplicationSteps,
    elements: tuple[_ProductElement, ...],
) -> tuple[_ProductStatement, ...]:
    """生成文を補助関数がポリシーより先になる順序へ並べる。"""
    statements: list[_ProductStatement] = []
    for statement in _ordered_generated_statements(generated, steps, elements):
        element = _element_for_statement(statement, elements)
        if statement.element_type == "predicate":
            continue
        sequence = _application_sequence(statement, steps, element)
        sql_text = statement.sql
        if statement.element_type == "function":
            from pitchlog.authz.first_ball_product import application_function_sql

            try:
                replacement = application_function_sql(statement.element_id, sql_text)
            except ValueError as error:
                raise ProductProvisioningError(str(error)) from error
            if replacement is not None:
                sql_text = replacement
        if statement.element_type == "schema" and _element_text(
            element, "schema_name"
        ) in {
            "rg1_control",
            "pitchlog_ledger_observer",
            "initial_right_api",
        }:
            sql_text = _strict_lifecycle_schema_sql(element, sql_text)
        if statement.element_type == "policy":
            table = _table_element(
                elements,
                _element_text(element, "table_id"),
            )
            qualified_table = _qualified_identifier(
                _element_text(table, "schema_name"),
                _element_text(table, "table_id"),
            )
            policy_name = _quote_identifier(_policy_name(element))
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
    if statement.element_type == "extension":
        return (
            "DROP EXTENSION IF EXISTS "
            f"{_quote_identifier(_element_text(element, 'extension_name'))};"
        )
    if statement.element_type == "function":
        qualified_function = _qualified_identifier(
            _element_text(element, "schema_name"),
            _element_text(element, "function_name"),
        )
        identity = f"{qualified_function}({_element_string(element, 'identity_args')})"
        function_kind = _element_text(element, "function_kind")
        if function_kind in {"rls_helper", "definer"}:
            return f"DROP FUNCTION IF EXISTS {identity};"
        if function_kind == "migration_function":
            # migration は関数を PUBLIC 実行可で作る。適用中に与えた直接 grant
            # を外してから PUBLIC を戻し、移行ロールの DROP ROLE 依存も残さない。
            revoke = f"REVOKE EXECUTE ON FUNCTION {identity} FROM %I CASCADE"
            revoke_literal = revoke.replace("'", "''")
            return f"""
DO $authz$
DECLARE
    grantee_name TEXT;
BEGIN
    FOR grantee_name IN
        SELECT role.rolname
        FROM pg_catalog.pg_proc AS procedure
        CROSS JOIN LATERAL pg_catalog.aclexplode(procedure.proacl) AS acl
        JOIN pg_catalog.pg_roles AS role ON role.oid = acl.grantee
        WHERE procedure.oid = pg_catalog.to_regprocedure('{identity}')
          AND acl.privilege_type = 'EXECUTE'
          AND acl.grantee <> procedure.proowner
    LOOP
        EXECUTE pg_catalog.format('{revoke_literal}', grantee_name);
    END LOOP;
END;
$authz$;
GRANT EXECUTE ON FUNCTION {identity} TO PUBLIC;
"""
        if (
            element.fields.get("function_id")
            == "FUNCTION:public:protect_initial_right_storage()"
        ):
            return f"REVOKE EXECUTE ON FUNCTION {identity} FROM PUBLIC;"
        if function_kind == "migration_trigger":
            return f"GRANT EXECUTE ON FUNCTION {identity} TO PUBLIC;"
        raise ProductProvisioningError(f"未知の製品関数種別: {function_kind}")
    if statement.element_type == "table":
        table = _qualified_identifier(
            _element_text(element, "schema_name"),
            _element_text(element, "table_id"),
        )
        if element.fields.get("table_id") in INITIAL_STORAGE_TABLES:
            return (
                f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
                f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;"
            )
        return f"""
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""
    if statement.element_type == "predicate":
        return None
    if statement.element_type == "policy":
        table = _table_element(elements, _element_text(element, "table_id"))
        policy_name = _quote_identifier(_policy_name(element))
        qualified_table = _qualified_identifier(
            _element_text(table, "schema_name"),
            _element_text(table, "table_id"),
        )
        return f"DROP POLICY IF EXISTS {policy_name} ON {qualified_table};"
    if statement.element_type == "acl_expectation":
        if element.fields.get("object_kind") == "builtin_function":
            from pitchlog.authz.product_function_acl import (
                is_builtin_execute_declaration,
            )

            if not is_builtin_execute_declaration(element.fields):
                raise ProductProvisioningError("builtin撤去の宣言がexact集合と不一致")
            grantee = _quote_identifier(_element_text(element, "grantee_role_id"))
            return (
                "REVOKE EXECUTE ON FUNCTION pg_catalog.pg_control_system() "
                f"FROM {grantee};"
            )
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
        from pitchlog.authz.initial_start_sql import is_start_column_acl

        if (
            is_initial_column_acl(element.fields)
            or is_start_column_acl(element.fields)
            or is_enrollment_column_acl(element.fields)
        ):
            privileges_value = element.fields["privilege_ids"]
            assert isinstance(privileges_value, list)
            privileges = ", ".join(
                f"{privilege} ({column})" for privilege in privileges_value
            )
        elif element.fields.get("grantee_role_id") in {
            "pitchlog_initial_fn_owner",
            "pitchlog_initial_actor",
            "pitchlog_app",
        }:
            raise ProductProvisioningError("初期主体の撤去列ACLが閉集合にない")
        elif (
            is_rg1_singleton_update_acl(element.fields)
            or is_rule_resolution_update_acl(element.fields)
            or (
                is_rg1_control_column_acl(element.fields)
                and element.fields.get("column_id") in {"state", "recovery_generation"}
            )
        ):
            privileges = f"SELECT ({column}), UPDATE ({column})"
        elif element.fields.get("privilege_ids") == ["SELECT"]:
            privileges = f"SELECT ({column})"
        else:
            raise ProductProvisioningError(
                "取り外し対象の列ACL権限が許可済み集合と一致しない"
            )
        return f"REVOKE {privileges} ON TABLE {table} FROM {grantee};"
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
    for statement in reversed(
        _ordered_generated_statements(generated, steps, elements)
    ):
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
                _ProductStatement(
                    sequence=len(steps.application_steps) + 1 - application_sequence,
                    sql=sql_text,
                )
            )
    return tuple(sorted(statements, key=lambda statement: statement.sequence))


def _build_operation_statements(
    operation: ProductOperation,
) -> tuple[ProductApplicationSteps, tuple[_ProductStatement, ...]]:
    """正規の置き場だけから手順と実行文を生成する。"""
    from pitchlog.authz.first_ball_product import (
        pre_rule_deferred_ids,
        validate,
    )

    candidate = json.loads(
        (_REPOSITORY_ROOT / PRODUCT_SPEC.ddl_elements_path).read_bytes()
    )
    try:
        added_profile = validate(candidate)
    except ValueError as error:
        raise ProductProvisioningError(str(error)) from error
    if added_profile and operation is ProductOperation.UNAPPLY:
        raise ProductProvisioningError(
            "同期binding履歴の退役は未提供。PUBLIC再付与/履歴削除を拒否する"
        )
    steps = load_product_application_steps(_REPOSITORY_ROOT, PRODUCT_SPEC)
    generated = generate_authz_ddl(_REPOSITORY_ROOT, PRODUCT_SPEC)
    if operation is ProductOperation.APPLY_PRE_RULE:
        deferred = {
            statement.element_id
            for statement in generated
            if statement.element_id == RULE_RESOLUTION_FUNCTION_ID
            or (
                statement.element_type == "column_acl_expectation"
                and statement.element_id.endswith(f":{RULE_RESOLUTION_OWNER_ROLE_ID}")
            )
        }
        if len(deferred) != 16 or RULE_RESOLUTION_FUNCTION_ID not in deferred:
            raise ProductProvisioningError("規則解決の保留対象がexact-set不一致")
        epoch_acl_id = (
            "COLUMN-ACL:public:rg1_restore_gate:recovery_generation:"
            "pitchlog_rg1_control_owner"
        )
        epoch_deferred = tuple(
            statement for statement in generated if statement.element_id == epoch_acl_id
        )
        if len(epoch_deferred) != 1 or (
            epoch_deferred[0].element_type != "column_acl_expectation"
        ):
            raise ProductProvisioningError("初回epoch列ACLの保留対象がexact-set不一致")
        deferred.add(epoch_acl_id)
        initial_deferred = frozenset(
            (
                "FUNCTION:initial_right_api:lock_device(uuid, uuid)",
                "FUNCTION:initial_right_api:read_existing_start(uuid, uuid, uuid)",
                "FUNCTION:initial_right_api:read_start_game(uuid, uuid)",
                "FUNCTION:initial_right_api:lock_preparing_game(uuid, uuid)",
                "FUNCTION:initial_right_api:lock_current_start(uuid, uuid, uuid)",
                "FUNCTION:initial_right_api:check_business_epoch(uuid, bigint)",
                (
                    "FUNCTION:initial_right_api:insert_initial_grant(uuid, u"
                    "uid, uuid, uuid, uuid, bigint, bigint, bytea, text, byt"
                    "ea, bytea)"
                ),
                (
                    "FUNCTION:initial_right_api:begin_start_attempt(uuid, uu"
                    "id, uuid, uuid, bytea, uuid)"
                ),
                (
                    "FUNCTION:initial_right_api:resolve_"
                    "start_attempt(uuid, uuid, uuid, uui"
                    "d)"
                ),
                "FUNCTION:public:protect_initial_right_storage()",
                "trusted_devices",
                "game_start_requests",
                "game_start_attempts",
                "recording_right_deliveries",
                "POLICY:trusted_devices:initial_right_trusted_devices_select",
                "POLICY:trusted_devices:initial_right_trusted_devices_update",
                "POLICY:game_start_requests:initial_right_game_start_requests_select",
                "POLICY:game_start_requests:initial_right_game_start_requests_insert",
                "POLICY:game_start_requests:initial_right_game_start_requests_update",
                "POLICY:game_start_attempts:initial_right_game_start_attempts_select",
                "POLICY:game_start_attempts:initial_right_game_start_attempts_insert",
                "POLICY:game_start_attempts:initial_right_game_start_attempts_update",
                (
                    "POLICY:recording_right_deliveries:initial_right_recordi"
                    "ng_right_deliveries_select"
                ),
                (
                    "POLICY:recording_right_deliveries:initial_right_recordi"
                    "ng_right_deliveries_insert"
                ),
                (
                    "POLICY:recording_right_deliveries:initial_right_recordi"
                    "ng_right_deliveries_update"
                ),
                "COLUMN-ACL:public:trusted_devices:tenant_id:pitchlog_initial_fn_owner",
                "COLUMN-ACL:public:trusted_devices:device_id:pitchlog_initial_fn_owner",
                (
                    "COLUMN-ACL:public:trusted_devices:credential_digest:pit"
                    "chlog_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:trusted_devices:r"
                    "evoked_at:pitchlog_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:game_start_requests:tenant_id:pitchlo"
                    "g_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:game_start_reques"
                    "ts:game_id:pitchlog_initial_fn_owne"
                    "r"
                ),
                (
                    "COLUMN-ACL:public:game_start_requests:start_request_id:"
                    "pitchlog_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:game_start_requests:device_id:pitchlo"
                    "g_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:game_start_requests:request_digest:pi"
                    "tchlog_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:game_start_attempts:tenant_id:pitchlo"
                    "g_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:game_start_attempts:attempt_id:pitchl"
                    "og_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:game_start_attemp"
                    "ts:game_id:pitchlog_initial_fn_owne"
                    "r"
                ),
                (
                    "COLUMN-ACL:public:game_start_attempts:start_request_id:"
                    "pitchlog_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:game_start_attempts:device_id:pitchlo"
                    "g_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:game_start_attemp"
                    "ts:outcome:pitchlog_initial_fn_owne"
                    "r"
                ),
                (
                    "COLUMN-ACL:public:game_start_attempts:resolved_at:pitch"
                    "log_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:recording_right_deliveries:tenant_id:"
                    "pitchlog_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:recording_right_deliveries:game_id:pi"
                    "tchlog_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:recording_right_deliveries:generation"
                    ":pitchlog_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:recording_right_deliveries:start_requ"
                    "est_id:pitchlog_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:recording_right_deliveries:device_id:"
                    "pitchlog_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:recording_right_deliveries:key_id:pit"
                    "chlog_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:recording_right_deliveries:nonce:pitc"
                    "hlog_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:recording_right_deliveries:ciphertext"
                    ":pitchlog_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:recording_right_deliveries:revoked_at"
                    ":pitchlog_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:recording_generations:proof_digest:pi"
                    "tchlog_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:recording_generations:recovery_genera"
                    "tion:pitchlog_initial_fn_owner"
                ),
                (
                    "COLUMN-ACL:public:rg1_restore_gate:recovery_generation:"
                    "pitchlog_initial_fn_owner"
                ),
            )
        )
        enrollment_dependencies = {
            "FUNCTION:initial_right_api:enroll_device(uuid, uuid, bytea)": "function",
            "POLICY:trusted_devices:initial_right_trusted_devices_insert": "policy",
        }
        has_enrollment = any(
            row.element_id in enrollment_dependencies for row in generated
        )
        if has_enrollment:
            initial_deferred = initial_deferred | frozenset(enrollment_dependencies)
        lookup_id = (
            "FUNCTION:initial_right_api:lookup_existing_start_attemp"
            "t(uuid, uuid, uuid, uuid, bytea)"
        )
        has_lookup = any(row.element_id == lookup_id for row in generated)
        if has_lookup:
            initial_deferred = initial_deferred | {lookup_id}
        actual_initial = {
            statement.element_id
            for statement in generated
            if statement.element_id in initial_deferred
        }
        if actual_initial != initial_deferred:
            raise ProductProvisioningError("初期保存の保留対象がexact-set不一致")
        from pitchlog.authz.initial_start_sql import (
            start_column_acl_declarations,
            start_function_declarations,
            start_policy_declarations,
        )

        new_dependencies = {
            **dict.fromkeys(start_column_acl_declarations(), "column_acl_expectation"),
            **dict.fromkeys(start_policy_declarations(), "policy"),
            **dict.fromkeys(start_function_declarations(), "function"),
        }
        has_start = any(row.element_id in new_dependencies for row in generated)
        deferred.update(initial_deferred)
        expected_dependencies = dict(_PRE_RULE_DEPENDENCIES)
        if not has_lookup:
            expected_dependencies.pop(lookup_id)
        if not has_enrollment:
            for key in enrollment_dependencies:
                expected_dependencies.pop(key)
        if has_start:
            deferred.update(new_dependencies)
            expected_dependencies.update(new_dependencies)
        selected = tuple(row for row in generated if row.element_id in deferred)
        if (
            len(selected) != len(expected_dependencies)
            or {row.element_id: row.element_type for row in selected}
            != expected_dependencies
            or deferred != set(expected_dependencies)
        ):
            raise ProductProvisioningError("前段保留70のID/種別/一意性が不一致")
        generated = tuple(
            statement for statement in generated if statement.element_id not in deferred
        )
    if added_profile and operation is ProductOperation.APPLY_PRE_RULE:
        deferred_binding = pre_rule_deferred_ids()
        generated = tuple(
            statement
            for statement in generated
            if statement.element_id not in deferred_binding
        )
    elements = _load_product_elements()
    if operation in (ProductOperation.APPLY, ProductOperation.APPLY_PRE_RULE):
        statements = _application_statements(generated, steps, elements)
    elif operation is ProductOperation.UNAPPLY:
        statements = _unapplication_statements(generated, steps, elements)
    else:  # pragma: no cover - Enum の閉包を型検査にも明示する。
        raise ProductProvisioningError(f"未定義の製品認可操作: {operation!r}")
    selected_steps = (
        steps.application_steps
        if operation in (ProductOperation.APPLY, ProductOperation.APPLY_PRE_RULE)
        else steps.unapplication_steps
    )
    if {statement.sequence for statement in statements} != {
        step.sequence for step in selected_steps
    }:
        raise ProductProvisioningError("製品認可の実行文が全手順を覆っていない")
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
    if operation in (ProductOperation.APPLY, ProductOperation.APPLY_PRE_RULE):
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


def _assert_connection_identity_parameters(
    connection: psycopg.Connection[Any],
) -> None:
    """SQL を実行せず接続時に通知された適用主体の前提を検査する。"""
    session_authorization = connection.info.parameter_status("session_authorization")
    is_superuser = connection.info.parameter_status("is_superuser")
    if not session_authorization:
        raise ProductProvisioningError("接続の session_authorization を取得できない")
    if session_authorization == "pitchlog_app":
        raise ProductProvisioningError("pitchlog_app は製品認可を適用できない")
    if is_superuser != "on":
        raise ProductProvisioningError(
            "製品認可の適用主体は superuser でなければならない"
        )


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
    _assert_connection_identity_parameters(connection)

    steps, statements = _build_operation_statements(operation)
    if steps.transaction != "single":
        raise ProductProvisioningError("製品認可の transaction は single が必要")
    _assert_no_subject_change(statements)

    transaction_started = False
    current_sequence = 1
    try:
        with connection.cursor() as cursor:
            for sequence in range(1, len(steps.application_steps) + 1):
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


_PRE_RULE_DEPENDENCIES: dict[str, str] = {
    (
        "FUNCTION:initial_right_api:lookup_existing_start_attemp"
        "t(uuid, uuid, uuid, uuid, bytea)"
    ): "function",
    ("FUNCTION:public:resolve_stage_a_rule(uuid, text, text, boolean)"): "function",
    "FUNCTION:initial_right_api:enroll_device(uuid, uuid, bytea)": "function",
    "POLICY:trusted_devices:initial_right_trusted_devices_insert": "policy",
    "FUNCTION:initial_right_api:lock_device(uuid, uuid)": "function",
    "FUNCTION:initial_right_api:read_existing_start(uuid, uuid, uuid)": "function",
    "FUNCTION:initial_right_api:read_start_game(uuid, uuid)": "function",
    "FUNCTION:initial_right_api:lock_preparing_game(uuid, uuid)": "function",
    "FUNCTION:initial_right_api:lock_current_start(uuid, uuid, uuid)": "function",
    "FUNCTION:initial_right_api:check_business_epoch(uuid, bigint)": "function",
    (
        "FUNCTION:initial_right_api:insert_i"
        "nitial_grant(uuid, uuid, uuid, uuid"
        ", uuid, bigint, bigint, bytea, text"
        ", bytea, bytea)"
    ): "function",
    (
        "FUNCTION:initial_right_api:begin_st"
        "art_attempt(uuid, uuid, uuid, uuid,"
        " bytea, uuid)"
    ): "function",
    (
        "FUNCTION:initial_right_api:resolve_start_attempt(uuid, uuid, uuid, uuid)"
    ): "function",
    "FUNCTION:public:protect_initial_right_storage()": "function",
    "trusted_devices": "table",
    "game_start_requests": "table",
    "game_start_attempts": "table",
    "recording_right_deliveries": "table",
    "POLICY:trusted_devices:initial_right_trusted_devices_select": "policy",
    "POLICY:trusted_devices:initial_right_trusted_devices_update": "policy",
    "POLICY:game_start_requests:initial_right_game_start_requests_select": "policy",
    "POLICY:game_start_requests:initial_right_game_start_requests_insert": "policy",
    "POLICY:game_start_requests:initial_right_game_start_requests_update": "policy",
    "POLICY:game_start_attempts:initial_right_game_start_attempts_select": "policy",
    "POLICY:game_start_attempts:initial_right_game_start_attempts_insert": "policy",
    "POLICY:game_start_attempts:initial_right_game_start_attempts_update": "policy",
    (
        "POLICY:recording_right_deliveries:i"
        "nitial_right_recording_right_delive"
        "ries_select"
    ): "policy",
    (
        "POLICY:recording_right_deliveries:i"
        "nitial_right_recording_right_delive"
        "ries_insert"
    ): "policy",
    (
        "POLICY:recording_right_deliveries:i"
        "nitial_right_recording_right_delive"
        "ries_update"
    ): "policy",
    (
        "COLUMN-ACL:public:game_type_rule_de"
        "faults:game_type_category:pitchlog_"
        "rule_resolution_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:game_type_rule_de"
        "faults:game_type_key:pitchlog_rule_"
        "resolution_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:game_type_rule_de"
        "faults:rule_set_id:pitchlog_rule_re"
        "solution_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:rule_sets:called_"
        "game_conditions:pitchlog_rule_resol"
        "ution_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:rule_sets:extra_i"
        "nnings_limit:pitchlog_rule_resoluti"
        "on_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:rule_sets:id:pitchlog_rule_resolution_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:rule_sets:regulat"
        "ion_innings:pitchlog_rule_resolutio"
        "n_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:rule_sets:tiebreak_rule:pitchlog_rule_resolution_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:rule_sets:uses_dh:pitchlog_rule_resolution_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:tenant_vocabulari"
        "es:category:pitchlog_rule_resolutio"
        "n_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:tenant_vocabulari"
        "es:disabled:pitchlog_rule_resolutio"
        "n_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:tenant_vocabularies:key:pitchlog_rule_resolution_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:tenant_vocabulari"
        "es:tenant_id:pitchlog_rule_resoluti"
        "on_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:tournament_rule_a"
        "ssignments:tenant_id:pitchlog_rule_"
        "resolution_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:tournament_rule_a"
        "ssignments:tournament_key:pitchlog_"
        "rule_resolution_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:rg1_restore_gate:"
        "recovery_generation:pitchlog_rg1_co"
        "ntrol_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:trusted_devices:tenant_id:pitchlog_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:trusted_devices:device_id:pitchlog_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:trusted_devices:credential_digest:pitchlog_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:trusted_devices:revoked_at:pitchlog_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:game_start_requests:tenant_id:pitchlog_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:game_start_requests:game_id:pitchlog_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:game_start_reques"
        "ts:start_request_id:pitchlog_initia"
        "l_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:game_start_requests:device_id:pitchlog_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:game_start_requests:request_digest:pitchlog_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:game_start_attempts:tenant_id:pitchlog_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:game_start_attempts:attempt_id:pitchlog_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:game_start_attempts:game_id:pitchlog_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:game_start_attemp"
        "ts:start_request_id:pitchlog_initia"
        "l_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:game_start_attempts:device_id:pitchlog_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:game_start_attempts:outcome:pitchlog_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:game_start_attempts:resolved_at:pitchlog_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:recording_right_d"
        "eliveries:tenant_id:pitchlog_initia"
        "l_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:recording_right_deliveries:game_id:pitchlog_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:recording_right_d"
        "eliveries:generation:pitchlog_initi"
        "al_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:recording_right_d"
        "eliveries:start_request_id:pitchlog"
        "_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:recording_right_d"
        "eliveries:device_id:pitchlog_initia"
        "l_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:recording_right_deliveries:key_id:pitchlog_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:recording_right_deliveries:nonce:pitchlog_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:recording_right_d"
        "eliveries:ciphertext:pitchlog_initi"
        "al_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:recording_right_d"
        "eliveries:revoked_at:pitchlog_initi"
        "al_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:recording_generations:proof_digest:pitchlog_initial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:recording_generat"
        "ions:recovery_generation:pitchlog_i"
        "nitial_fn_owner"
    ): "column_acl_expectation",
    (
        "COLUMN-ACL:public:rg1_restore_gate:"
        "recovery_generation:pitchlog_initia"
        "l_fn_owner"
    ): "column_acl_expectation",
}
