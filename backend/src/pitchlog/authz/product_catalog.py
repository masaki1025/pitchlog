"""製品認可資産と実 PostgreSQL カタログを exact-set で照合する。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, LiteralString

import psycopg

from pitchlog.authz.asset_spec import (
    PRODUCT_SPEC,
    ProductApplicationSteps,
    load_product_application_steps,
)

_REPOSITORY_ROOT = Path(__file__).parents[4]
_SQL_TOKEN_RE = re.compile(
    r"'(?:''|[^'])*'|\$[a-zA-Z_0-9]*\$|::|<=|>=|<>|!=|:=|=>|"
    r"[a-zA-Z_][a-zA-Z_0-9$]*|\d+(?:\.\d+)?|[-+*/%=<>,.\[\]()]"
)
_SQL_LINE_COMMENT_RE = re.compile(r"--[^\n]*(?:\n|$)")
_SQL_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

_ROLES_QUERY: LiteralString = """
SELECT role.oid, role.rolname, role.rolsuper, role.rolbypassrls,
       role.rolcanlogin, role.rolcreaterole, role.rolcreatedb,
       role.rolreplication, role.rolinherit
FROM pg_catalog.pg_roles AS role
WHERE role.rolname = ANY(%s)
ORDER BY role.rolname
"""

_DATABASE_QUERY: LiteralString = """
SELECT database.datname, owner.rolname
FROM pg_catalog.pg_database AS database
JOIN pg_catalog.pg_roles AS owner ON owner.oid = database.datdba
WHERE database.datname = pg_catalog.current_database()
"""

_DATABASE_ACL_QUERY: LiteralString = """
SELECT COALESCE(grantee.rolname, 'PUBLIC'), privilege.privilege_type,
       privilege.is_grantable
FROM pg_catalog.pg_database AS database
CROSS JOIN LATERAL pg_catalog.aclexplode(database.datacl) AS privilege
LEFT JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = privilege.grantee
WHERE database.datname = pg_catalog.current_database()
  AND privilege.grantee <> database.datdba
ORDER BY 1, 2, 3
"""

_SCHEMAS_QUERY: LiteralString = """
SELECT namespace.nspname,
       CASE
           WHEN owner.rolname = 'pg_database_owner' THEN database_owner.rolname
           ELSE owner.rolname
       END
FROM pg_catalog.pg_namespace AS namespace
JOIN pg_catalog.pg_roles AS owner ON owner.oid = namespace.nspowner
JOIN pg_catalog.pg_database AS database
  ON database.datname = pg_catalog.current_database()
JOIN pg_catalog.pg_roles AS database_owner ON database_owner.oid = database.datdba
WHERE namespace.nspname = ANY(%s)
ORDER BY namespace.nspname
"""

_SCHEMA_ACL_QUERY: LiteralString = """
SELECT namespace.nspname, COALESCE(grantee.rolname, 'PUBLIC'),
       privilege.privilege_type, privilege.is_grantable
FROM pg_catalog.pg_namespace AS namespace
CROSS JOIN LATERAL pg_catalog.aclexplode(namespace.nspacl) AS privilege
LEFT JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = privilege.grantee
WHERE namespace.nspname = ANY(%s)
  AND privilege.grantee <> namespace.nspowner
ORDER BY 1, 2, 3, 4
"""

_TABLES_QUERY: LiteralString = """
SELECT namespace.nspname, relation.relname, owner.rolname,
       relation.relrowsecurity, relation.relforcerowsecurity
FROM pg_catalog.pg_class AS relation
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
JOIN pg_catalog.pg_roles AS owner ON owner.oid = relation.relowner
WHERE namespace.nspname = ANY(%s)
  AND relation.relname = ANY(%s)
  AND relation.relkind IN ('r', 'p')
ORDER BY namespace.nspname, relation.relname
"""

_POLICIES_QUERY: LiteralString = """
WITH original_search_path AS MATERIALIZED (
    SELECT pg_catalog.current_setting('search_path') AS value
),
catalog_search_path AS MATERIALIZED (
    SELECT pg_catalog.set_config('search_path', 'pg_catalog', true) AS value
    FROM original_search_path
),
observed_policies AS MATERIALIZED (
    SELECT namespace.nspname, relation.relname, policy.polname, policy.polcmd,
           ARRAY(
               SELECT COALESCE(role.rolname, 'PUBLIC')
               FROM pg_catalog.unnest(policy.polroles) AS member(role_oid)
               LEFT JOIN pg_catalog.pg_roles AS role ON role.oid = member.role_oid
               ORDER BY COALESCE(role.rolname, 'PUBLIC')
           ) AS roles,
           policy.polpermissive,
           pg_catalog.pg_get_expr(policy.polqual, policy.polrelid) AS using_expr,
           pg_catalog.pg_get_expr(
               policy.polwithcheck,
               policy.polrelid
           ) AS with_check_expr
    FROM pg_catalog.pg_policy AS policy
    JOIN pg_catalog.pg_class AS relation ON relation.oid = policy.polrelid
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = relation.relnamespace
    CROSS JOIN catalog_search_path
    WHERE namespace.nspname = ANY(%s)
      AND relation.relname = ANY(%s)
      AND catalog_search_path.value = 'pg_catalog'
),
restored_search_path AS MATERIALIZED (
    SELECT pg_catalog.set_config(
               'search_path',
               original_search_path.value,
               completed_observation.observed_count >= 0
           ) AS value
    FROM original_search_path
    CROSS JOIN (
        SELECT pg_catalog.count(*) AS observed_count
        FROM observed_policies
    ) AS completed_observation
)
SELECT observed_policies.nspname,
       observed_policies.relname,
       observed_policies.polname,
       observed_policies.polcmd,
       observed_policies.roles,
       observed_policies.polpermissive,
       observed_policies.using_expr,
       observed_policies.with_check_expr
FROM observed_policies
CROSS JOIN restored_search_path
WHERE restored_search_path.value IS NOT NULL
ORDER BY observed_policies.nspname,
         observed_policies.relname,
         observed_policies.polname
"""

_TABLE_ACL_QUERY: LiteralString = """
SELECT namespace.nspname, relation.relname,
       COALESCE(grantee.rolname, 'PUBLIC'), privilege.privilege_type,
       privilege.is_grantable
FROM pg_catalog.pg_class AS relation
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
CROSS JOIN LATERAL pg_catalog.aclexplode(relation.relacl) AS privilege
LEFT JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = privilege.grantee
WHERE namespace.nspname = ANY(%s)
  AND relation.relname = ANY(%s)
  AND relation.relkind IN ('r', 'p')
  AND privilege.grantee <> relation.relowner
ORDER BY 1, 2, 3, 4, 5
"""

_COLUMN_ACL_QUERY: LiteralString = """
SELECT namespace.nspname, relation.relname, attribute.attname,
       COALESCE(grantee.rolname, 'PUBLIC'), privilege.privilege_type,
       privilege.is_grantable
FROM pg_catalog.pg_attribute AS attribute
JOIN pg_catalog.pg_class AS relation ON relation.oid = attribute.attrelid
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
CROSS JOIN LATERAL pg_catalog.aclexplode(attribute.attacl) AS privilege
LEFT JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = privilege.grantee
WHERE namespace.nspname = ANY(%s)
  AND relation.relname = ANY(%s)
  AND attribute.attnum > 0
  AND NOT attribute.attisdropped
  AND privilege.grantee <> relation.relowner
ORDER BY 1, 2, attribute.attnum, 4, 5, 6
"""

_FUNCTIONS_QUERY: LiteralString = """
SELECT namespace.nspname, routine.proname,
       pg_catalog.oidvectortypes(routine.proargtypes),
       owner.rolname, routine.prosecdef
FROM pg_catalog.pg_proc AS routine
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = routine.pronamespace
JOIN pg_catalog.pg_roles AS owner ON owner.oid = routine.proowner
WHERE namespace.nspname = ANY(%s)
  AND routine.proname = ANY(%s)
ORDER BY namespace.nspname, routine.proname,
         pg_catalog.oidvectortypes(routine.proargtypes)
"""

_FUNCTION_ACL_QUERY: LiteralString = """
SELECT namespace.nspname, routine.proname,
       pg_catalog.oidvectortypes(routine.proargtypes),
       COALESCE(grantee.rolname, 'PUBLIC'), privilege.privilege_type,
       privilege.is_grantable
FROM pg_catalog.pg_proc AS routine
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = routine.pronamespace
CROSS JOIN LATERAL pg_catalog.aclexplode(routine.proacl) AS privilege
LEFT JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = privilege.grantee
WHERE namespace.nspname = ANY(%s)
  AND routine.proname = ANY(%s)
  AND privilege.grantee <> routine.proowner
ORDER BY 1, 2, 3, 4, 5, 6
"""

_MEMBERSHIPS_QUERY: LiteralString = """
SELECT granted.rolname, member.rolname, grantor.rolname,
       membership.admin_option, membership.inherit_option, membership.set_option
FROM pg_catalog.pg_auth_members AS membership
JOIN pg_catalog.pg_roles AS granted ON granted.oid = membership.roleid
JOIN pg_catalog.pg_roles AS member ON member.oid = membership.member
JOIN pg_catalog.pg_roles AS grantor ON grantor.oid = membership.grantor
WHERE granted.rolname = ANY(%s) OR member.rolname = ANY(%s)
ORDER BY granted.rolname, member.rolname, grantor.rolname
"""

_DANGEROUS_LOGIN_ROLES_QUERY: LiteralString = """
SELECT role.oid, role.rolname
FROM pg_catalog.pg_roles AS role
WHERE role.rolcanlogin
  AND (
      role.rolsuper
      OR role.rolbypassrls
      OR EXISTS (
          SELECT 1
          FROM pg_catalog.pg_database AS database
          WHERE database.datname = pg_catalog.current_database()
            AND database.datdba = role.oid
      )
      OR EXISTS (
          SELECT 1
          FROM pg_catalog.pg_namespace AS namespace
          WHERE namespace.nspname = ANY(%s)
            AND namespace.nspowner = role.oid
      )
      OR EXISTS (
          SELECT 1
          FROM pg_catalog.pg_class AS relation
          JOIN pg_catalog.pg_namespace AS namespace
            ON namespace.oid = relation.relnamespace
          WHERE namespace.nspname = ANY(%s)
            AND relation.relname = ANY(%s)
            AND relation.relowner = role.oid
      )
      OR EXISTS (
          SELECT 1
          FROM pg_catalog.pg_proc AS routine
          JOIN pg_catalog.pg_namespace AS namespace
            ON namespace.oid = routine.pronamespace
          WHERE namespace.nspname = ANY(%s)
            AND routine.proname = ANY(%s)
            AND routine.proowner = role.oid
      )
  )
ORDER BY role.oid
"""


class ProductCatalogError(RuntimeError):
    """製品カタログの入力または観測を安全に検査できないことを表す。"""


class CatalogQueryId(Enum):
    """製品カタログ末端が受け付ける閉じた問い合わせ ID。"""

    ROLES = "roles"
    DATABASE = "database"
    DATABASE_ACL = "database_acl"
    SCHEMAS = "schemas"
    SCHEMA_ACL = "schema_acl"
    TABLES = "tables"
    POLICIES = "policies"
    TABLE_ACL = "table_acl"
    COLUMN_ACL = "column_acl"
    FUNCTIONS = "functions"
    FUNCTION_ACL = "function_acl"
    MEMBERSHIPS = "memberships"
    DANGEROUS_LOGIN_ROLES = "dangerous_login_roles"


@dataclass(frozen=True, slots=True)
class ProductCatalogViolation:
    """資産期待値とカタログ観測値の不一致を表す。"""

    check_id: str
    expected: object
    actual: object


@dataclass(frozen=True, slots=True)
class ProductCatalogReport:
    """実施した製品カタログ検査と全違反を保持する。"""

    checked_ids: tuple[str, ...]
    violations: tuple[ProductCatalogViolation, ...]

    @property
    def ok(self) -> bool:
        """すべての exact-set 検査が一致したか返す。"""
        return not self.violations


@dataclass(frozen=True, slots=True)
class _CatalogRequest:
    """閉じた問い合わせ ID と束縛値を保持する。"""

    query_id: CatalogQueryId
    params: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class _ProductExpectations:
    """製品資産から導出した全カタログ期待値を保持する。"""

    application_steps: ProductApplicationSteps
    role_ids: tuple[str, ...]
    roles: tuple[tuple[object, ...], ...]
    database_owner: str
    database_acl: tuple[tuple[object, ...], ...]
    schema_names: tuple[str, ...]
    schemas: tuple[tuple[object, ...], ...]
    schema_acl: tuple[tuple[object, ...], ...]
    table_names: tuple[str, ...]
    tables: tuple[tuple[object, ...], ...]
    policies: tuple[tuple[object, ...], ...]
    table_acl: tuple[tuple[object, ...], ...]
    column_acl: tuple[tuple[object, ...], ...]
    function_names: tuple[str, ...]
    functions: tuple[tuple[object, ...], ...]
    function_acl: tuple[tuple[object, ...], ...]
    trigger_function_keys: tuple[tuple[str, str, str], ...]


class _ReportBuilder:
    """検査 ID の一意性を守って製品カタログの差分を蓄積する。"""

    def __init__(self) -> None:
        """空の検査結果を初期化する。"""
        self._checked_ids: list[str] = []
        self._violations: list[ProductCatalogViolation] = []

    def compare(self, check_id: str, expected: object, actual: object) -> None:
        """期待値と実値を照合し、不一致だけを記録する。"""
        if check_id in self._checked_ids:
            raise ProductCatalogError(f"製品カタログの検査 ID が重複: {check_id}")
        self._checked_ids.append(check_id)
        if expected != actual:
            self._violations.append(
                ProductCatalogViolation(
                    check_id=check_id,
                    expected=expected,
                    actual=actual,
                )
            )

    def build(self) -> ProductCatalogReport:
        """不変の公開結果を返す。"""
        return ProductCatalogReport(
            checked_ids=tuple(self._checked_ids),
            violations=tuple(self._violations),
        )


def _rows(asset: dict[str, object], key: str) -> tuple[dict[str, object], ...]:
    """資産の object 配列を検証して返す。"""
    value = asset[key] if key in asset else None
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ProductCatalogError(f"製品資産の {key} は object 配列でなければならない")
    return tuple(row for row in value if isinstance(row, dict))


def _text(row: dict[str, object], key: str, label: str) -> str:
    """資産行から空でない文字列を読む。"""
    value = row[key] if key in row else None
    if not isinstance(value, str) or not value:
        raise ProductCatalogError(f"{label}.{key} は空でない文字列が必要")
    return value


def _boolean(row: dict[str, object], key: str, label: str) -> bool:
    """資産行から真偽値を読む。"""
    value = row[key] if key in row else None
    if not isinstance(value, bool):
        raise ProductCatalogError(f"{label}.{key} は boolean が必要")
    return value


def _strings(row: dict[str, object], key: str, label: str) -> tuple[str, ...]:
    """資産行から空でない文字列の配列を読む。"""
    value = row[key] if key in row else None
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ProductCatalogError(f"{label}.{key} は文字列配列が必要")
    result = tuple(item for item in value if isinstance(item, str))
    if len(result) != len(set(result)):
        raise ProductCatalogError(f"{label}.{key} は重複できない")
    return result


def _optional_text(row: dict[str, object], key: str, label: str) -> str | None:
    """資産行から null または空でない文字列を読む。"""
    value = row[key] if key in row else None
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ProductCatalogError(f"{label}.{key} は null か空でない文字列が必要")
    return value


def _strip_sql_comments(source: str) -> str:
    """式の意味に含まれない SQL コメントを除く。"""
    return _SQL_LINE_COMMENT_RE.sub(" ", _SQL_BLOCK_COMMENT_RE.sub(" ", source))


def _semantic_sql_tokens(source: str | None) -> tuple[str, ...] | None:
    """Deparser の括弧と組込み型 cast を吸収して式を正規化する。"""
    if source is None:
        return None
    uncommented = _strip_sql_comments(source).replace("pg_catalog.", "")
    raw_tokens = _SQL_TOKEN_RE.findall(uncommented)
    lowered = [
        token if token.startswith(("'", "$")) else token.casefold()
        for token in raw_tokens
    ]
    result: list[str] = []
    index = 0
    while index < len(lowered):
        token = lowered[index]
        if token in {"(", ")", "as"}:
            index += 1
            continue
        if token == "::" and index + 1 < len(lowered):
            previous = lowered[index - 1] if index else ""
            cast_end = index + 2
            if cast_end + 1 < len(lowered) and lowered[cast_end : cast_end + 2] == [
                "[",
                "]",
            ]:
                cast_end += 2
            is_literal_cast = (
                previous.startswith("'")
                or previous.replace(".", "", 1).isdigit()
                or previous in {"null", "true", "false", "]"}
            )
            if not is_literal_cast:
                result.extend(lowered[index:cast_end])
            index = cast_end
            continue
        result.append(token)
        index += 1
    return tuple(result)


def _direct_acl(
    row: dict[str, object],
    key: str,
    label: str,
) -> tuple[tuple[str, str, bool], ...]:
    """DB・schema・function の直接 ACL 宣言を正規化する。"""
    raw_entries = row[key] if key in row else None
    if not isinstance(raw_entries, list) or not all(
        isinstance(entry, dict) for entry in raw_entries
    ):
        raise ProductCatalogError(f"{label}.{key} は object 配列が必要")
    result: list[tuple[str, str, bool]] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        grantee = _text(raw_entry, "grantee", f"{label}.{key}")
        privilege = _text(raw_entry, "privilege", f"{label}.{key}").upper()
        grantable = _boolean(raw_entry, "grantable", f"{label}.{key}")
        result.append((grantee, privilege, grantable))
    if len(result) != len(set(result)):
        raise ProductCatalogError(f"{label}.{key} が重複している")
    return tuple(sorted(result))


def _schema_for_table(tables: tuple[dict[str, object], ...], table_id: str) -> str:
    """表 ID に対応する一意な schema 名を返す。"""
    matches = tuple(
        _text(table, "schema_name", "tables")
        for table in tables
        if _text(table, "table_id", "tables") == table_id
    )
    if len(matches) != 1:
        raise ProductCatalogError(f"表の schema を一意に導出できない: {table_id}")
    return matches[0]


def _load_product_asset() -> dict[str, object]:
    """正規の staged 製品資産を JSON object として読む。"""
    asset_path = _REPOSITORY_ROOT / PRODUCT_SPEC.ddl_elements_path
    try:
        with open(asset_path, encoding="utf-8") as asset_file:
            value = json.load(asset_file)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProductCatalogError(f"製品認可資産を読めない: {error}") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ProductCatalogError("製品認可資産は JSON object が必要")
    return value


def _load_product_expectations() -> _ProductExpectations:
    """Staged 資産と適用手順資産から exact-set 期待値を導出する。"""
    asset = _load_product_asset()
    application_steps = load_product_application_steps(_REPOSITORY_ROOT, PRODUCT_SPEC)

    role_rows = _rows(asset, "roles")
    roles = tuple(
        sorted(
            (
                _text(row, "role_id", "roles"),
                _boolean(row, "superuser", "roles"),
                _boolean(row, "bypass_rls", "roles"),
                _boolean(row, "login", "roles"),
                _boolean(row, "create_role", "roles"),
                _boolean(row, "create_db", "roles"),
                _boolean(row, "replication", "roles"),
                _boolean(row, "inherit", "roles"),
            )
            for row in role_rows
        )
    )
    role_ids = tuple(row[0] for row in roles if isinstance(row[0], str))
    if len(role_ids) != len(set(role_ids)):
        raise ProductCatalogError("製品ロール ID が重複している")
    membership_edges = (
        asset["membership_edges"] if "membership_edges" in asset else None
    )
    if membership_edges != []:
        raise ProductCatalogError("製品ロールに接する membership 辺は 0 本が必要")

    database_rows = _rows(asset, "databases")
    if len(database_rows) != 1:
        raise ProductCatalogError("製品 database 宣言は 1 件が必要")
    database = database_rows[0]
    database_owner = _text(database, "owner", "databases")
    database_acl = _direct_acl(database, "acl_expectations", "databases")

    schema_rows = _rows(asset, "schemas")
    schemas = tuple(
        sorted(
            (
                _text(row, "schema_name", "schemas"),
                _text(row, "owner", "schemas"),
            )
            for row in schema_rows
        )
    )
    schema_names = tuple(row[0] for row in schemas)
    schema_acl_entries: list[tuple[object, ...]] = []
    for row in schema_rows:
        schema_name = _text(row, "schema_name", "schemas")
        for grantee, privilege, grantable in _direct_acl(
            row, "acl_expectations", "schemas"
        ):
            schema_acl_entries.append((schema_name, grantee, privilege, grantable))

    table_rows = _rows(asset, "tables")
    tables = tuple(
        sorted(
            (
                _text(row, "schema_name", "tables"),
                _text(row, "table_id", "tables"),
                database_owner,
                _boolean(row, "enable_row_level_security", "tables"),
                _boolean(row, "force_row_level_security", "tables"),
            )
            for row in table_rows
        )
    )
    table_names = tuple(row[1] for row in tables)

    policies = tuple(
        sorted(
            (
                _schema_for_table(
                    table_rows,
                    _text(row, "table_id", "policies"),
                ),
                _text(row, "table_id", "policies"),
                f"pitchlog_app_{_text(row, 'profile', 'policies')}",
                _text(row, "command", "policies").casefold(),
                tuple(sorted(_strings(row, "role_ids", "policies"))),
                _text(row, "policy_mode", "policies").casefold(),
                _semantic_sql_tokens(
                    _optional_text(row, "using_expression", "policies")
                ),
                _semantic_sql_tokens(
                    _optional_text(row, "with_check_expression", "policies")
                ),
            )
            for row in _rows(asset, "policies")
        )
    )

    table_acl_entries: list[tuple[object, ...]] = []
    for row in _rows(asset, "acl_expectations"):
        if _text(row, "object_kind", "acl_expectations") != "table":
            raise ProductCatalogError("製品の object ACL は table だけを許可する")
        schema_name = _text(row, "object_schema", "acl_expectations")
        table_id = _text(row, "object_id", "acl_expectations")
        grantee = _text(row, "grantee_role_id", "acl_expectations")
        grantable = _boolean(row, "grant_option", "acl_expectations")
        for privilege in _strings(row, "privilege_ids", "acl_expectations"):
            table_acl_entries.append(
                (schema_name, table_id, grantee, privilege.upper(), grantable)
            )

    column_acl_entries: list[tuple[object, ...]] = []
    for row in _rows(asset, "column_acl_expectations"):
        if _text(row, "object_kind", "column_acl_expectations") != "column":
            raise ProductCatalogError("製品の列 ACL は column だけを許可する")
        schema_name = _text(row, "object_schema", "column_acl_expectations")
        table_id = _text(row, "object_id", "column_acl_expectations")
        column_id = _text(row, "column_id", "column_acl_expectations")
        grantee = _text(row, "grantee_role_id", "column_acl_expectations")
        grantable = _boolean(row, "grant_option", "column_acl_expectations")
        for privilege in _strings(row, "privilege_ids", "column_acl_expectations"):
            column_acl_entries.append(
                (
                    schema_name,
                    table_id,
                    column_id,
                    grantee,
                    privilege.upper(),
                    grantable,
                )
            )

    functions: list[tuple[object, ...]] = []
    function_acl_entries: list[tuple[object, ...]] = []
    trigger_function_keys: list[tuple[str, str, str]] = []
    function_names: list[str] = []
    for row in _rows(asset, "functions"):
        schema_name = _text(row, "schema_name", "functions")
        function_name = _text(row, "function_name", "functions")
        identity_args = (
            _text(row, "identity_args", "functions") if row.get("identity_args") else ""
        )
        owner = _text(row, "owner_role_id", "functions")
        function_kind = _text(row, "function_kind", "functions")
        security_definer = row.get("security_mode") == "definer"
        key = (schema_name, function_name, identity_args)
        functions.append((*key, owner, security_definer))
        function_names.append(function_name)
        if function_kind == "migration_trigger":
            trigger_function_keys.append(key)
        elif function_kind != "rls_helper":
            raise ProductCatalogError(f"未知の製品関数種別: {function_kind}")
        for grantee, privilege, grantable in _direct_acl(
            row, "acl_expectations", "functions"
        ):
            function_acl_entries.append((*key, grantee, privilege, grantable))

    return _ProductExpectations(
        application_steps=application_steps,
        role_ids=role_ids,
        roles=roles,
        database_owner=database_owner,
        database_acl=database_acl,
        schema_names=schema_names,
        schemas=schemas,
        schema_acl=tuple(sorted(schema_acl_entries)),
        table_names=table_names,
        tables=tables,
        policies=policies,
        table_acl=tuple(sorted(table_acl_entries)),
        column_acl=tuple(sorted(column_acl_entries)),
        function_names=tuple(sorted(set(function_names))),
        functions=tuple(sorted(functions)),
        function_acl=tuple(sorted(function_acl_entries)),
        trigger_function_keys=tuple(sorted(trigger_function_keys)),
    )


def _catalog_requests(
    expectations: _ProductExpectations,
) -> tuple[_CatalogRequest, ...]:
    """全問い合わせ ID と資産由来の束縛値を固定順で返す。"""
    schemas = list(expectations.schema_names)
    tables = list(expectations.table_names)
    functions = list(expectations.function_names)
    roles = list(expectations.role_ids)
    return (
        _CatalogRequest(CatalogQueryId.ROLES, (roles,)),
        _CatalogRequest(CatalogQueryId.DATABASE, ()),
        _CatalogRequest(CatalogQueryId.DATABASE_ACL, ()),
        _CatalogRequest(CatalogQueryId.SCHEMAS, (schemas,)),
        _CatalogRequest(CatalogQueryId.SCHEMA_ACL, (schemas,)),
        _CatalogRequest(CatalogQueryId.TABLES, (schemas, tables)),
        _CatalogRequest(CatalogQueryId.POLICIES, (schemas, tables)),
        _CatalogRequest(CatalogQueryId.TABLE_ACL, (schemas, tables)),
        _CatalogRequest(CatalogQueryId.COLUMN_ACL, (schemas, tables)),
        _CatalogRequest(CatalogQueryId.FUNCTIONS, (schemas, functions)),
        _CatalogRequest(CatalogQueryId.FUNCTION_ACL, (schemas, functions)),
        _CatalogRequest(CatalogQueryId.MEMBERSHIPS, (roles, roles)),
        _CatalogRequest(
            CatalogQueryId.DANGEROUS_LOGIN_ROLES,
            (schemas, schemas, tables, schemas, functions),
        ),
    )


def _query_for_id(query_id: CatalogQueryId) -> LiteralString:
    """閉じた問い合わせ ID をモジュール固定 SQL へ対応付ける。"""
    if query_id is CatalogQueryId.ROLES:
        return _ROLES_QUERY
    if query_id is CatalogQueryId.DATABASE:
        return _DATABASE_QUERY
    if query_id is CatalogQueryId.DATABASE_ACL:
        return _DATABASE_ACL_QUERY
    if query_id is CatalogQueryId.SCHEMAS:
        return _SCHEMAS_QUERY
    if query_id is CatalogQueryId.SCHEMA_ACL:
        return _SCHEMA_ACL_QUERY
    if query_id is CatalogQueryId.TABLES:
        return _TABLES_QUERY
    if query_id is CatalogQueryId.POLICIES:
        return _POLICIES_QUERY
    if query_id is CatalogQueryId.TABLE_ACL:
        return _TABLE_ACL_QUERY
    if query_id is CatalogQueryId.COLUMN_ACL:
        return _COLUMN_ACL_QUERY
    if query_id is CatalogQueryId.FUNCTIONS:
        return _FUNCTIONS_QUERY
    if query_id is CatalogQueryId.FUNCTION_ACL:
        return _FUNCTION_ACL_QUERY
    if query_id is CatalogQueryId.MEMBERSHIPS:
        return _MEMBERSHIPS_QUERY
    if query_id is CatalogQueryId.DANGEROUS_LOGIN_ROLES:
        return _DANGEROUS_LOGIN_ROLES_QUERY
    raise ProductCatalogError(f"未知の製品カタログ問い合わせ ID: {query_id!r}")


def _fetch_catalog_rows(
    connection: psycopg.Connection[Any],
    query_id: CatalogQueryId,
    params: tuple[object, ...],
) -> list[tuple[object, ...]]:
    """閉じた ID の固定 SQL を実行して行を返す読み取り専用末端。"""
    query = _query_for_id(query_id)
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return [tuple(row) for row in cursor]


def _observed_rows(
    observations: tuple[tuple[CatalogQueryId, tuple[tuple[object, ...], ...]], ...],
    query_id: CatalogQueryId,
) -> tuple[tuple[object, ...], ...]:
    """一意な問い合わせ ID の観測行を返す。"""
    matches = tuple(
        rows for observed_id, rows in observations if observed_id is query_id
    )
    if len(matches) != 1:
        raise ProductCatalogError(f"製品カタログ観測値が一意でない: {query_id.value}")
    return matches[0]


def _actual_roles(
    rows: tuple[tuple[object, ...], ...],
) -> tuple[tuple[object, ...], ...]:
    """ロール観測行を期待値と同じ 7 属性へ正規化する。"""
    return tuple(
        sorted(
            (
                str(row[1]),
                bool(row[2]),
                bool(row[3]),
                bool(row[4]),
                bool(row[5]),
                bool(row[6]),
                bool(row[7]),
                bool(row[8]),
            )
            for row in rows
        )
    )


def _integer(value: object, label: str) -> int:
    """PostgreSQL の整数観測値を bool と区別して返す。"""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProductCatalogError(f"{label} は整数でなければならない")
    return value


def _owner_role_oid(rows: tuple[tuple[object, ...], ...], owner_role_id: str) -> int:
    """固定 owner ロールの OID をロール観測値から導出する。"""
    matches = tuple(
        _integer(row[0], "role.oid") for row in rows if str(row[1]) == owner_role_id
    )
    return matches[0] if len(matches) == 1 else -1


def _actual_database_owner(
    rows: tuple[tuple[object, ...], ...],
) -> str | None:
    """現在 DB の owner を一意な観測行から返す。"""
    return str(rows[0][1]) if len(rows) == 1 else None


def _actual_acl(
    rows: tuple[tuple[object, ...], ...], prefix_columns: int
) -> tuple[tuple[object, ...], ...]:
    """ACL 観測値の privilege と grantable を正規化する。"""
    result: list[tuple[object, ...]] = []
    for row in rows:
        prefix = tuple(str(value) for value in row[:prefix_columns])
        result.append(
            (
                *prefix,
                str(row[prefix_columns]).upper(),
                bool(row[prefix_columns + 1]),
            )
        )
    return tuple(sorted(result))


def _actual_schemas(
    rows: tuple[tuple[object, ...], ...],
) -> tuple[tuple[object, ...], ...]:
    """Schema 名と実効 owner を正規化する。"""
    return tuple(sorted((str(row[0]), str(row[1])) for row in rows))


def _actual_tables(
    rows: tuple[tuple[object, ...], ...],
) -> tuple[tuple[object, ...], ...]:
    """表の owner・ENABLE・FORCE を正規化する。"""
    return tuple(
        sorted(
            (
                str(row[0]),
                str(row[1]),
                str(row[2]),
                bool(row[3]),
                bool(row[4]),
            )
            for row in rows
        )
    )


def _policy_command(value: object) -> str:
    """Pg_policy の 1 文字コマンドを資産の語へ正規化する。"""
    command = str(value)
    if command == "*":
        return "all"
    if command == "r":
        return "select"
    if command == "a":
        return "insert"
    if command == "w":
        return "update"
    if command == "d":
        return "delete"
    return command.casefold()


def _actual_policies(
    rows: tuple[tuple[object, ...], ...],
) -> tuple[tuple[object, ...], ...]:
    """Pg_policy のコマンド・roles・式を正規化する。"""
    result: list[tuple[object, ...]] = []
    for row in rows:
        raw_roles = row[4]
        if not isinstance(raw_roles, (list, tuple)):
            raise ProductCatalogError("pg_policy.polroles の観測値が配列でない")
        result.append(
            (
                str(row[0]),
                str(row[1]),
                str(row[2]),
                _policy_command(row[3]),
                tuple(sorted(str(role) for role in raw_roles)),
                "permissive" if bool(row[5]) else "restrictive",
                _semantic_sql_tokens(None if row[6] is None else str(row[6])),
                _semantic_sql_tokens(None if row[7] is None else str(row[7])),
            )
        )
    return tuple(sorted(result))


def _actual_functions(
    rows: tuple[tuple[object, ...], ...],
) -> tuple[tuple[object, ...], ...]:
    """関数 identity・owner・security mode を正規化する。"""
    return tuple(
        sorted(
            (
                str(row[0]),
                str(row[1]),
                str(row[2]),
                str(row[3]),
                bool(row[4]),
            )
            for row in rows
        )
    )


def _actual_trigger_definers(
    rows: tuple[tuple[object, ...], ...],
    trigger_keys: tuple[tuple[str, str, str], ...],
) -> tuple[tuple[str, str, str], ...]:
    """Security definer になった migration trigger 関数だけを返す。"""
    return tuple(
        sorted(
            (str(row[0]), str(row[1]), str(row[2]))
            for row in rows
            if (str(row[0]), str(row[1]), str(row[2])) in trigger_keys and bool(row[4])
        )
    )


def _actual_memberships(
    rows: tuple[tuple[object, ...], ...],
) -> tuple[tuple[object, ...], ...]:
    """製品ロールに接する membership 辺を全 option 付きで正規化する。"""
    return tuple(
        sorted(
            (
                str(row[0]),
                str(row[1]),
                str(row[2]),
                bool(row[3]),
                bool(row[4]),
                bool(row[5]),
            )
            for row in rows
        )
    )


def _validate_privileged_role_oids(privileged_role_oids: frozenset[int]) -> None:
    """環境入力の superuser OID 集合を fail-closed に検証する。"""
    if not isinstance(privileged_role_oids, frozenset) or not privileged_role_oids:
        raise ProductCatalogError("privileged_role_oids は空でない frozenset が必要")
    if any(
        not isinstance(role_oid, int) or isinstance(role_oid, bool) or role_oid <= 0
        for role_oid in privileged_role_oids
    ):
        raise ProductCatalogError("privileged_role_oids は正の整数だけを許可する")


def inspect_product_authz_catalog(
    connection: psycopg.Connection[Any],
    *,
    privileged_role_oids: frozenset[int],
) -> ProductCatalogReport:
    """実カタログを製品資産と exact-set 照合する。"""
    _validate_privileged_role_oids(privileged_role_oids)
    expectations = _load_product_expectations()
    observations: list[tuple[CatalogQueryId, tuple[tuple[object, ...], ...]]] = []
    try:
        for request in _catalog_requests(expectations):
            rows = _fetch_catalog_rows(
                connection,
                request.query_id,
                request.params,
            )
            observations.append((request.query_id, tuple(rows)))
    except psycopg.Error as error:
        raise ProductCatalogError(f"製品カタログを観測できない: {error}") from error

    frozen_observations = tuple(observations)
    role_rows = _observed_rows(frozen_observations, CatalogQueryId.ROLES)
    function_rows = _observed_rows(frozen_observations, CatalogQueryId.FUNCTIONS)
    report = _ReportBuilder()
    report.compare(
        "PRODUCT-CATALOG:ROLES",
        expectations.roles,
        _actual_roles(role_rows),
    )
    report.compare(
        "PRODUCT-CATALOG:DATABASE-OWNER",
        expectations.database_owner,
        _actual_database_owner(
            _observed_rows(frozen_observations, CatalogQueryId.DATABASE)
        ),
    )
    report.compare(
        "PRODUCT-CATALOG:DATABASE-ACL",
        expectations.database_acl,
        _actual_acl(
            _observed_rows(frozen_observations, CatalogQueryId.DATABASE_ACL),
            1,
        ),
    )
    report.compare(
        "PRODUCT-CATALOG:SCHEMAS",
        expectations.schemas,
        _actual_schemas(_observed_rows(frozen_observations, CatalogQueryId.SCHEMAS)),
    )
    report.compare(
        "PRODUCT-CATALOG:SCHEMA-ACL",
        expectations.schema_acl,
        _actual_acl(
            _observed_rows(frozen_observations, CatalogQueryId.SCHEMA_ACL),
            2,
        ),
    )
    report.compare(
        "PRODUCT-CATALOG:TABLES",
        expectations.tables,
        _actual_tables(_observed_rows(frozen_observations, CatalogQueryId.TABLES)),
    )
    report.compare(
        "PRODUCT-CATALOG:POLICIES",
        expectations.policies,
        _actual_policies(_observed_rows(frozen_observations, CatalogQueryId.POLICIES)),
    )
    report.compare(
        "PRODUCT-CATALOG:TABLE-ACL",
        expectations.table_acl,
        _actual_acl(
            _observed_rows(frozen_observations, CatalogQueryId.TABLE_ACL),
            3,
        ),
    )
    report.compare(
        "PRODUCT-CATALOG:COLUMN-ACL",
        expectations.column_acl,
        _actual_acl(
            _observed_rows(frozen_observations, CatalogQueryId.COLUMN_ACL),
            4,
        ),
    )
    report.compare(
        "PRODUCT-CATALOG:FUNCTIONS",
        expectations.functions,
        _actual_functions(function_rows),
    )
    report.compare(
        "PRODUCT-CATALOG:FUNCTION-ACL",
        expectations.function_acl,
        _actual_acl(
            _observed_rows(frozen_observations, CatalogQueryId.FUNCTION_ACL),
            4,
        ),
    )
    report.compare(
        "PRODUCT-CATALOG:MEMBERSHIPS",
        (),
        _actual_memberships(
            _observed_rows(frozen_observations, CatalogQueryId.MEMBERSHIPS)
        ),
    )
    report.compare(
        "PRODUCT-CATALOG:TRIGGER-SECURITY-INVOKER",
        (),
        _actual_trigger_definers(function_rows, expectations.trigger_function_keys),
    )
    owner_oid = _owner_role_oid(role_rows, "pitchlog_owner")
    expected_dangerous_oids = tuple(sorted((*privileged_role_oids, owner_oid)))
    actual_dangerous_oids = tuple(
        sorted(
            _integer(row[0], "dangerous_role.oid")
            for row in _observed_rows(
                frozen_observations,
                CatalogQueryId.DANGEROUS_LOGIN_ROLES,
            )
        )
    )
    report.compare(
        "PRODUCT-CATALOG:DANGEROUS-LOGIN-ROLES",
        expected_dangerous_oids,
        actual_dangerous_oids,
    )
    return report.build()
