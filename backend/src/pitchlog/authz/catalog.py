"""認可資産と実 PostgreSQL カタログを照合する。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, LiteralString

import psycopg

from pitchlog.authz.ddl import (
    DDL_ELEMENTS_PATH,
    AuthzDDLGenerationError,
    DDLStatement,
    generate_authz_ddl,
)

_POLICY_RE = re.compile(
    r"(?is)\bCREATE\s+POLICY\s+(?P<policy>[a-z_][a-z0-9_]*)\s+"
    r"ON\s+(?P<schema>[a-z_][a-z0-9_]*)\.(?P<table>[a-z_][a-z0-9_]*)\b"
)
_FUNCTION_CREATE_RE = re.compile(r"(?im)^\s*CREATE\s+FUNCTION\b")
_FUNCTION_TRAILER_RE = re.compile(r"(?im)^\s*ALTER\s+FUNCTION\b")
_ALTER_FUNCTION_TARGET_RE = re.compile(
    r"(?is)\bALTER\s+FUNCTION\s+(.+?)\s+OWNER\s+TO\b"
)
_LANGUAGE_RE = re.compile(r"(?i)\bLANGUAGE\s+([a-z_][a-z0-9_]*)\b")
_VOLATILITY_RE = re.compile(r"(?i)\b(IMMUTABLE|STABLE|VOLATILE)\b")
_PARALLEL_RE = re.compile(r"(?i)\bPARALLEL\s+(SAFE|RESTRICTED|UNSAFE)\b")
_DYNAMIC_SQL_PATTERNS = (
    re.compile(r"(?i)\bEXECUTE\b"),
    re.compile(r"(?i)\bformat\s*\("),
    re.compile(r"\|\|"),
)
_SQL_TOKEN_RE = re.compile(
    r"'(?:''|[^'])*'|\$[a-zA-Z_0-9]*\$|::|<=|>=|<>|!=|:=|=>|"
    r"[a-zA-Z_][a-zA-Z_0-9$]*|\d+(?:\.\d+)?|[-+*/%=<>,.\[\]()]"
)


class CatalogCheckError(Exception):
    """カタログ検査を開始または完了できない入力不正を表す。

    Attributes:
        check_id: 入力不正を識別する検査 ID。
    """

    def __init__(self, message: str, check_id: str = "CATALOG:INPUT") -> None:
        """検査 ID と説明を保持する。"""
        super().__init__(message)
        self.check_id = check_id


@dataclass(frozen=True, slots=True)
class CatalogViolation:
    """資産期待値とカタログ観測値の不一致を表す。

    Attributes:
        check_id: ``CATALOG:`` から始まる検査 ID。
        expected: 資産から導出した正規化済み期待値。
        actual: PostgreSQL から観測した正規化済み実値。
    """

    check_id: str
    expected: object
    actual: object


@dataclass(frozen=True, slots=True)
class CatalogReport:
    """実施した検査と違反を保持する。

    Attributes:
        checked_ids: 実行した検査 ID の一意な安定順列。
        violations: 資産との不一致。空なら合格。
    """

    checked_ids: tuple[str, ...]
    violations: tuple[CatalogViolation, ...]

    @property
    def ok(self) -> bool:
        """すべてのカタログ検査が一致したか返す。"""
        return not self.violations


@dataclass(frozen=True, slots=True)
class _FunctionObservation:
    """関数カタログの digest 対象 10 属性を保持する。"""

    oid: int
    identity_arguments: str
    definition: str
    owner: str
    language: str
    security_definer: bool
    volatility: str
    leakproof: bool
    strict: bool
    parallel: str
    config: tuple[str, ...]
    acl: tuple[tuple[str, str, bool], ...]


class _ReportBuilder:
    """検査 ID の一意性を守りながら照合結果を蓄積する。"""

    def __init__(self) -> None:
        """空の検査結果を初期化する。"""
        self._checked_ids: list[str] = []
        self._violations: list[CatalogViolation] = []

    def compare(self, check_id: str, expected: object, actual: object) -> None:
        """1 検査を記録し、異なる場合だけ違反を追加する。"""
        if check_id in self._checked_ids:
            raise CatalogCheckError(f"検査IDが重複している: {check_id}")
        self._checked_ids.append(check_id)
        if expected != actual:
            self._violations.append(
                CatalogViolation(
                    check_id=check_id,
                    expected=expected,
                    actual=actual,
                )
            )

    def build(self) -> CatalogReport:
        """不変の公開結果を返す。"""
        return CatalogReport(
            checked_ids=tuple(self._checked_ids),
            violations=tuple(self._violations),
        )


def _read_json_object(path: Path, label: str) -> dict[str, object]:
    """JSON object を読み、入力不正を単一例外へ変換する。"""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CatalogCheckError(f"{label}を読めない: {path}: {error}") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CatalogCheckError(f"{label}はJSON objectでなければならない")
    return value


def _rows(asset: dict[str, object], key: str) -> tuple[dict[str, object], ...]:
    """資産の object 配列を型確認して返す。"""
    value = asset.get(key)
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise CatalogCheckError(f"ddl-elements.{key}はobject配列でなければならない")
    return tuple(row for row in value if isinstance(row, dict))


def _text(value: object, label: str) -> str:
    """空でない文字列を要求する。"""
    if not isinstance(value, str) or not value:
        raise CatalogCheckError(f"{label}は空でない文字列でなければならない")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    """重複のない文字列配列を要求する。"""
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise CatalogCheckError(f"{label}は空でない文字列だけの配列でなければならない")
    result = tuple(item for item in value if isinstance(item, str))
    if len(result) != len(set(result)):
        raise CatalogCheckError(f"{label}に重複がある")
    return result


def _strip_sql_comments(source: str) -> str:
    """SQL の行コメントとブロックコメントを正規化前に除く。"""
    without_blocks = re.sub(r"/\*.*?\*/", " ", source, flags=re.DOTALL)
    return re.sub(r"(?m)--.*$", " ", without_blocks)


def _semantic_sql_tokens(source: str) -> tuple[str, ...]:
    """Deparser が付加する括弧・組込み型 cast を吸収して SQL を正規化する。"""
    source = _strip_sql_comments(source).replace("pg_catalog.", "")
    raw_tokens = _SQL_TOKEN_RE.findall(source)
    lowered = [
        token if token.startswith(("'", "$")) else token.casefold()
        for token in raw_tokens
    ]
    result: list[str] = []
    index = 0
    while index < len(lowered):
        token = lowered[index]
        if token in {"(", ")"}:
            index += 1
            continue
        if token == "as":
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


def _balanced_clause(source: str, marker: re.Pattern[str], label: str) -> str:
    """Marker 直後の括弧句を文字列リテラルを尊重して切り出す。"""
    match = marker.search(source)
    if match is None:
        raise CatalogCheckError(f"{label}をbodyから導出できない")
    opening = source.find("(", match.start())
    if opening < 0:
        raise CatalogCheckError(f"{label}の開始括弧がない")
    depth = 0
    in_string = False
    index = opening
    while index < len(source):
        character = source[index]
        following = source[index + 1 : index + 2]
        if in_string:
            if character == "'" and following == "'":
                index += 2
                continue
            if character == "'":
                in_string = False
        elif character == "'":
            in_string = True
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return source[opening + 1 : index]
        index += 1
    raise CatalogCheckError(f"{label}の終了括弧がない")


def _function_create_source(statement: DDLStatement) -> str:
    """封印済み body から CREATE FUNCTION 部分だけを取り出す。"""
    create = _FUNCTION_CREATE_RE.search(statement.sql)
    trailer = _FUNCTION_TRAILER_RE.search(statement.sql)
    if create is None or trailer is None or create.start() >= trailer.start():
        raise CatalogCheckError(
            f"関数bodyのCREATE部分を導出できない: {statement.element_id}"
        )
    return statement.sql[create.start() : trailer.start()].strip()


def _function_regprocedure(statement: DDLStatement) -> str:
    """封印済み ALTER FUNCTION から identity signature を導出する。"""
    target = _ALTER_FUNCTION_TARGET_RE.search(statement.sql)
    if target is None:
        raise CatalogCheckError(
            f"function bodyからowner対象を導出できない: {statement.element_id}"
        )
    return re.sub(r"\s+", " ", target.group(1)).strip()


def _digest(attributes: dict[str, object]) -> str:
    """正規化済み 10 属性を安定した SHA-256 へ畳み込む。"""
    encoded = json.dumps(
        attributes,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _function_acl_expectation(
    asset: dict[str, object], function_id: str
) -> tuple[tuple[str, str, bool], ...]:
    """ACL 資産から関数の非 owner ACL を導出する。"""
    entries: list[tuple[str, str, bool]] = []
    for row in _rows(asset, "acl_expectations"):
        if row.get("object_kind") != "function" or row.get("object_id") != function_id:
            continue
        role_id = _text(row.get("grantee_role_id"), "acl.grantee_role_id")
        grant_option = row.get("grant_option")
        if not isinstance(grant_option, bool):
            raise CatalogCheckError("acl.grant_optionはbooleanでなければならない")
        for privilege in _strings(row.get("privilege_ids"), "acl.privilege_ids"):
            entries.append((role_id, privilege.upper(), grant_option))
    return tuple(sorted(entries))


def _expected_function_attributes(
    asset: dict[str, object],
    function: dict[str, object],
    statement: DDLStatement,
    reference_definition: str,
) -> dict[str, object]:
    """参照 DB・封印済み body・資産から関数の 10 属性を導出する。"""
    function_id = _text(function.get("function_id"), "functions.function_id")
    source = _function_create_source(statement)
    uncommented = _strip_sql_comments(source)
    language_match = _LANGUAGE_RE.search(uncommented)
    volatility_match = _VOLATILITY_RE.search(uncommented)
    if language_match is None or volatility_match is None:
        raise CatalogCheckError(f"関数属性をbodyから導出できない: {function_id}")
    parallel_match = _PARALLEL_RE.search(uncommented)
    config = _strings(function.get("search_path"), "functions.search_path")
    return {
        "definition": reference_definition,
        "owner": _text(function.get("owner_role_id"), "functions.owner_role_id"),
        "language": language_match.group(1).casefold(),
        "security": function.get("security_mode") == "definer",
        "volatility": volatility_match.group(1).casefold(),
        "leakproof": bool(re.search(r"(?i)\bLEAKPROOF\b", uncommented)),
        "strict": bool(
            re.search(
                r"(?i)\bSTRICT\b|\bRETURNS\s+NULL\s+ON\s+NULL\s+INPUT\b",
                uncommented,
            )
        ),
        "parallel": (
            parallel_match.group(1).casefold()
            if parallel_match is not None
            else "unsafe"
        ),
        "config": (f"search_path={', '.join(config)}",),
        "acl": _function_acl_expectation(asset, function_id),
    }


def _actual_function_attributes(observation: _FunctionObservation) -> dict[str, object]:
    """カタログ観測値を期待値と同じ 10 属性へ正規化する。"""
    volatility = {"i": "immutable", "s": "stable", "v": "volatile"}.get(
        observation.volatility,
        observation.volatility,
    )
    parallel = {"s": "safe", "r": "restricted", "u": "unsafe"}.get(
        observation.parallel,
        observation.parallel,
    )
    return {
        "definition": observation.definition,
        "owner": observation.owner,
        "language": observation.language.casefold(),
        "security": observation.security_definer,
        "volatility": volatility,
        "leakproof": observation.leakproof,
        "strict": observation.strict,
        "parallel": parallel,
        "config": observation.config,
        "acl": observation.acl,
    }


def _observe_functions(
    connection: psycopg.Connection[Any], schemas: tuple[str, ...]
) -> dict[tuple[str, str], tuple[_FunctionObservation, ...]]:
    """対象 schema の関数 10 属性と全 overload を観測する。"""
    query = """
        SELECT routine.oid,
               namespace.nspname,
               routine.proname,
               pg_catalog.pg_get_function_identity_arguments(routine.oid),
               pg_catalog.pg_get_functiondef(routine.oid),
               owner.rolname,
               language.lanname,
               routine.prosecdef,
               routine.provolatile,
               routine.proleakproof,
               routine.proisstrict,
               routine.proparallel,
               COALESCE(routine.proconfig, ARRAY[]::text[])
        FROM pg_catalog.pg_proc AS routine
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = routine.pronamespace
        JOIN pg_catalog.pg_roles AS owner
          ON owner.oid = routine.proowner
        JOIN pg_catalog.pg_language AS language
          ON language.oid = routine.prolang
        WHERE namespace.nspname = ANY(%s)
        ORDER BY namespace.nspname,
                 routine.proname,
                 pg_catalog.pg_get_function_identity_arguments(routine.oid)
    """
    observed: dict[tuple[str, str], list[_FunctionObservation]] = {}
    with connection.cursor() as cursor:
        cursor.execute(query, (list(schemas),))
        rows = cursor.fetchall()
        for row in rows:
            oid = int(row[0])
            cursor.execute(
                """
                SELECT COALESCE(grantee.rolname, 'PUBLIC'),
                       privilege.privilege_type,
                       privilege.is_grantable
                FROM pg_catalog.pg_proc AS routine
                CROSS JOIN LATERAL pg_catalog.aclexplode(routine.proacl) AS privilege
                LEFT JOIN pg_catalog.pg_roles AS grantee
                  ON grantee.oid = privilege.grantee
                WHERE routine.oid = %s
                  AND privilege.grantee <> routine.proowner
                ORDER BY 1, 2, 3
                """,
                (oid,),
            )
            acl = tuple(
                (str(item[0]), str(item[1]).upper(), bool(item[2]))
                for item in cursor.fetchall()
            )
            observation = _FunctionObservation(
                oid=oid,
                identity_arguments=str(row[3]),
                definition=str(row[4]),
                owner=str(row[5]),
                language=str(row[6]),
                security_definer=bool(row[7]),
                volatility=str(row[8]),
                leakproof=bool(row[9]),
                strict=bool(row[10]),
                parallel=str(row[11]),
                config=tuple(str(value) for value in row[12]),
                acl=acl,
            )
            observed.setdefault((str(row[1]), str(row[2])), []).append(observation)
    return {key: tuple(value) for key, value in observed.items()}


def _database_identity(connection: psycopg.Connection[Any]) -> tuple[str, str]:
    """接続先クラスタと database の識別子を読む。"""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT control.system_identifier::text,
                   pg_catalog.current_database()
            FROM pg_catalog.pg_control_system() AS control
            """
        )
        row = cursor.fetchone()
    if row is None:
        raise CatalogCheckError(
            "参照DBのクラスタ識別子を観測できない",
            check_id="CATALOG:FUNCTION-DIGEST:REFERENCE",
        )
    return str(row[0]), str(row[1])


def _sealed_reference_function_definitions(
    root: Path,
    target_connection: psycopg.Connection[Any],
    reference_connection: psycopg.Connection[Any],
    functions: tuple[dict[str, object], ...],
) -> tuple[
    dict[tuple[str, str], DDLStatement],
    dict[tuple[str, str], str],
]:
    """封印済み DDL を適用した別 DB から definition 期待値を読む。

    参照カタログを読む前に ``generate_authz_ddl`` を実行し、その内部の
    manifest 現物・source commit 二段照合を必須にする。
    """
    try:
        generated = generate_authz_ddl(root)
    except AuthzDDLGenerationError as error:
        raise CatalogCheckError(
            f"封印済みfunction bodyを検証できない: {error}",
            check_id="CATALOG:FUNCTION-DIGEST:SOURCE-SEAL",
        ) from error
    sealed_statements = {
        (statement.element_type, statement.element_id): statement
        for statement in generated
    }
    target_cluster, target_database = _database_identity(target_connection)
    reference_cluster, reference_database = _database_identity(reference_connection)
    if target_cluster != reference_cluster or target_database == reference_database:
        raise CatalogCheckError(
            "definition参照値は同一クラスタ内の別databaseから読む必要がある",
            check_id="CATALOG:FUNCTION-DIGEST:REFERENCE",
        )

    expected_keys = {
        (
            _text(row.get("schema_id"), "functions.schema_id"),
            _text(row.get("function_id"), "functions.function_id"),
        )
        for row in functions
    }
    if any(
        ("function", function_id) not in sealed_statements
        for _, function_id in expected_keys
    ):
        raise CatalogCheckError(
            "二段封印済みfunction bodyが参照値の対象集合と一致しない",
            check_id="CATALOG:FUNCTION-DIGEST:REFERENCE",
        )
    reference_rows = _observe_functions(
        reference_connection,
        tuple(sorted({schema_id for schema_id, _ in expected_keys})),
    )
    if set(reference_rows) != expected_keys or any(
        len(rows) != 1 for rows in reference_rows.values()
    ):
        raise CatalogCheckError(
            "参照databaseのfunction集合が資産とexact-set一致しない",
            check_id="CATALOG:FUNCTION-DIGEST:REFERENCE",
        )
    definitions = {key: rows[0].definition for key, rows in reference_rows.items()}
    return sealed_statements, definitions


def _check_policies(
    connection: psycopg.Connection[Any],
    asset: dict[str, object],
    statements: dict[tuple[str, str], DDLStatement],
    report: _ReportBuilder,
) -> None:
    """pg_policy の 5 属性を全 policy について exact 照合する。"""
    tables = {
        _text(row.get("table_id"), "tables.table_id"): row
        for row in _rows(asset, "tables")
    }
    predicates = {
        _text(row.get("predicate_id"), "predicates.predicate_id")
        for row in _rows(asset, "predicates")
    }
    expected: dict[tuple[str, str, str], tuple[object, ...]] = {}
    using_marker = re.compile(r"(?i)\bUSING\s*\(")
    check_marker = re.compile(r"(?i)\bWITH\s+CHECK\s*\(")
    for policy in _rows(asset, "policies"):
        policy_id = _text(policy.get("policy_id"), "policies.policy_id")
        table_id = _text(policy.get("table_id"), "policies.table_id")
        table = tables.get(table_id)
        if table is None:
            raise CatalogCheckError(f"policyのtable_idが未定義: {policy_id}")
        for field in ("using_predicate_id", "with_check_predicate_id"):
            if _text(policy.get(field), f"policies.{field}") not in predicates:
                raise CatalogCheckError(f"policyのpredicateが未定義: {policy_id}")
        statement = statements.get(("policy", policy_id))
        if statement is None:
            raise CatalogCheckError(f"policy bodyがない: {policy_id}")
        match = _POLICY_RE.search(statement.sql)
        if match is None:
            raise CatalogCheckError(f"policy bodyの識別子を導出できない: {policy_id}")
        schema_id = _text(table.get("schema_id"), "tables.schema_id")
        if (match.group("schema"), match.group("table")) != (schema_id, table_id):
            raise CatalogCheckError(f"policy bodyと資産の対象表が不一致: {policy_id}")
        command = _text(policy.get("command"), "policies.command").casefold()
        mode = _text(policy.get("policy_mode"), "policies.policy_mode").casefold()
        expected[(schema_id, table_id, match.group("policy"))] = (
            command,
            tuple(sorted(_strings(policy.get("role_ids"), "policies.role_ids"))),
            mode,
            _semantic_sql_tokens(
                _balanced_clause(statement.sql, using_marker, f"{policy_id}.USING")
            ),
            _semantic_sql_tokens(
                _balanced_clause(statement.sql, check_marker, f"{policy_id}.WITH CHECK")
            ),
        )

    actual: dict[tuple[str, str, str], tuple[object, ...]] = {}
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT namespace.nspname,
                   relation.relname,
                   policy.polname,
                   policy.polcmd,
                   ARRAY(
                       SELECT COALESCE(role.rolname, 'PUBLIC')
                       FROM pg_catalog.unnest(policy.polroles) AS member(role_oid)
                       LEFT JOIN pg_catalog.pg_roles AS role
                         ON role.oid = member.role_oid
                       ORDER BY COALESCE(role.rolname, 'PUBLIC')
                   ),
                   policy.polpermissive,
                   pg_catalog.pg_get_expr(policy.polqual, policy.polrelid),
                   pg_catalog.pg_get_expr(policy.polwithcheck, policy.polrelid)
            FROM pg_catalog.pg_policy AS policy
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = policy.polrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE relation.relname = ANY(%s)
              AND namespace.nspname = ANY(%s)
            ORDER BY 1, 2, 3
            """,
            (
                list(tables),
                sorted(
                    {
                        _text(row.get("schema_id"), "tables.schema_id")
                        for row in tables.values()
                    }
                ),
            ),
        )
        for row in cursor.fetchall():
            command = {
                "*": "all",
                "r": "select",
                "a": "insert",
                "w": "update",
                "d": "delete",
            }.get(str(row[3]), str(row[3]))
            actual[(str(row[0]), str(row[1]), str(row[2]))] = (
                command,
                tuple(str(role) for role in row[4]),
                "permissive" if bool(row[5]) else "restrictive",
                _semantic_sql_tokens(str(row[6])),
                _semantic_sql_tokens(str(row[7])),
            )
    expected_keys = tuple(sorted(expected))
    actual_keys = tuple(sorted(actual))
    report.compare("CATALOG:POLICY:EXACT-SET", expected_keys, actual_keys)
    for key in expected_keys:
        policy_id = next(
            _text(row.get("policy_id"), "policies.policy_id")
            for row in _rows(asset, "policies")
            if row.get("table_id") == key[1]
        )
        report.compare(f"CATALOG:{policy_id}", expected[key], actual.get(key))


def _check_functions(
    connection: psycopg.Connection[Any],
    asset: dict[str, object],
    statements: dict[tuple[str, str], DDLStatement],
    reference_definitions: dict[tuple[str, str], str],
    report: _ReportBuilder,
) -> dict[tuple[str, str], tuple[_FunctionObservation, ...]]:
    """関数 digest・構造・search_path を照合する。"""
    functions = _rows(asset, "functions")
    schema_ids = tuple(
        sorted(
            {_text(row.get("schema_id"), "functions.schema_id") for row in functions}
        )
    )
    observations = _observe_functions(connection, schema_ids)
    expected_keys = tuple(
        sorted(
            (
                _text(row.get("schema_id"), "functions.schema_id"),
                _text(row.get("function_id"), "functions.function_id"),
            )
            for row in functions
        )
    )
    report.compare(
        "CATALOG:FUNCTION-DIGEST:EXACT-SET",
        expected_keys,
        tuple(sorted(observations)),
    )
    table_schemas = {
        _text(row.get("table_id"), "tables.table_id"): _text(
            row.get("schema_id"), "tables.schema_id"
        )
        for row in _rows(asset, "tables")
    }
    for function in functions:
        function_id = _text(function.get("function_id"), "functions.function_id")
        schema_id = _text(function.get("schema_id"), "functions.schema_id")
        statement = statements.get(("function", function_id))
        if statement is None:
            raise CatalogCheckError(f"function bodyがない: {function_id}")
        rows = observations.get((schema_id, function_id), ())
        reference_definition = reference_definitions.get((schema_id, function_id))
        if reference_definition is None:
            raise CatalogCheckError(
                f"参照databaseにfunction definitionがない: {function_id}",
                check_id="CATALOG:FUNCTION-DIGEST:REFERENCE",
            )
        expected_attributes = _expected_function_attributes(
            asset,
            function,
            statement,
            reference_definition,
        )
        actual_attributes = (
            _actual_function_attributes(rows[0]) if len(rows) == 1 else None
        )
        report.compare(
            f"CATALOG:FUNCTION-DIGEST:{function_id}",
            _digest(expected_attributes),
            _digest(actual_attributes) if actual_attributes is not None else None,
        )
        source = rows[0].definition if len(rows) == 1 else ""
        language_atomic = (
            len(rows) == 1
            and rows[0].language.casefold() == "sql"
            and re.search(r"(?i)\bBEGIN\s+ATOMIC\b", source) is not None
        )
        report.compare(
            f"CATALOG:FUNCTION-STRUCTURE:{function_id}:SQL-ATOMIC",
            True,
            language_atomic,
        )
        dynamic_hits = tuple(
            pattern.pattern
            for pattern in _DYNAMIC_SQL_PATTERNS
            if pattern.search(_strip_sql_comments(source)) is not None
        )
        report.compare(
            f"CATALOG:FUNCTION-STRUCTURE:{function_id}:NO-DYNAMIC-SQL",
            (),
            dynamic_hits,
        )
        expected_relations = tuple(
            sorted(
                (
                    table_schemas[table_id],
                    table_id,
                )
                for table_id in _strings(
                    function.get("dependency_table_ids"),
                    "functions.dependency_table_ids",
                )
            )
        )
        actual_relations: tuple[tuple[str, str], ...] = ()
        if len(rows) == 1:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT namespace.nspname, relation.relname
                    FROM pg_catalog.pg_depend AS dependency
                    JOIN pg_catalog.pg_class AS relation
                      ON relation.oid = dependency.refobjid
                    JOIN pg_catalog.pg_namespace AS namespace
                      ON namespace.oid = relation.relnamespace
                    WHERE dependency.classid = 'pg_catalog.pg_proc'::regclass
                      AND dependency.objid = %s
                      AND dependency.refclassid = 'pg_catalog.pg_class'::regclass
                    ORDER BY 1, 2
                    """,
                    (rows[0].oid,),
                )
                actual_relations = tuple(
                    (str(row[0]), str(row[1])) for row in cursor.fetchall()
                )
        report.compare(
            f"CATALOG:FUNCTION-STRUCTURE:{function_id}:DEPENDENCY-RELATIONS",
            expected_relations,
            actual_relations,
        )
        expected_path = _strings(function.get("search_path"), "functions.search_path")
        actual_path: tuple[str, ...] = ()
        if len(rows) == 1:
            settings = [
                value.removeprefix("search_path=")
                for value in rows[0].config
                if value.startswith("search_path=")
            ]
            if len(settings) == 1:
                actual_path = tuple(part.strip() for part in settings[0].split(","))
        report.compare(
            f"CATALOG:SEARCH-PATH:{function_id}",
            (
                expected_path,
                expected_path[-1:] == ("pg_temp",),
                expected_path.count("pg_temp"),
            ),
            (
                actual_path,
                actual_path[-1:] == ("pg_temp",),
                actual_path.count("pg_temp"),
            ),
        )
    return observations


def _caller_role_ids(asset: dict[str, object]) -> tuple[str, ...]:
    """到達閉包の始点を資産の caller 種別から導出する。"""
    caller_kinds = {"tested_caller", "management_caller", "negative_test_caller"}
    return tuple(
        _text(row.get("role_id"), "roles.role_id")
        for row in _rows(asset, "roles")
        if row.get("role_kind") in caller_kinds
    )


def _dangerous_role_ids(
    connection: psycopg.Connection[Any], asset: dict[str, object]
) -> tuple[str, ...]:
    """属性と保護 object 所有者から危険終点を観測する。"""
    schema_ids = tuple(
        _text(row.get("schema_id"), "schemas.schema_id")
        for row in _rows(asset, "schemas")
    )
    table_ids = tuple(
        _text(row.get("table_id"), "tables.table_id") for row in _rows(asset, "tables")
    )
    function_ids = tuple(
        _text(row.get("function_id"), "functions.function_id")
        for row in _rows(asset, "functions")
    )
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT role.rolname
            FROM pg_catalog.pg_roles AS role
            WHERE role.rolsuper OR role.rolbypassrls
            UNION
            SELECT owner.rolname
            FROM pg_catalog.pg_namespace AS namespace
            JOIN pg_catalog.pg_roles AS owner ON owner.oid = namespace.nspowner
            WHERE namespace.nspname = ANY(%s)
            UNION
            SELECT owner.rolname
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_roles AS owner ON owner.oid = relation.relowner
            WHERE relation.relname = ANY(%s)
            UNION
            SELECT owner.rolname
            FROM pg_catalog.pg_proc AS routine
            JOIN pg_catalog.pg_roles AS owner ON owner.oid = routine.proowner
            WHERE routine.proname = ANY(%s)
            ORDER BY 1
            """,
            (list(schema_ids), list(table_ids), list(function_ids)),
        )
        return tuple(str(row[0]) for row in cursor.fetchall())


def _reachable_dangerous_roles(
    connection: psycopg.Connection[Any],
    callers: tuple[str, ...],
    dangerous: tuple[str, ...],
    mode: str,
) -> tuple[tuple[str, str], ...]:
    """SET または USAGE の辺だけで到達する危険ロールを計算する。"""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            WITH RECURSIVE reachable(start_oid, role_oid) AS (
                SELECT role.oid, role.oid
                FROM pg_catalog.pg_roles AS role
                WHERE role.rolname = ANY(%s)
                UNION
                SELECT reachable.start_oid, membership.roleid
                FROM reachable
                JOIN pg_catalog.pg_auth_members AS membership
                  ON membership.member = reachable.role_oid
                WHERE (%s = 'SET' AND membership.set_option)
                   OR (%s = 'USAGE' AND membership.inherit_option)
            )
            SELECT starter.rolname, endpoint.rolname
            FROM reachable
            JOIN pg_catalog.pg_roles AS starter
              ON starter.oid = reachable.start_oid
            JOIN pg_catalog.pg_roles AS endpoint
              ON endpoint.oid = reachable.role_oid
            WHERE endpoint.rolname = ANY(%s)
            ORDER BY 1, 2
            """,
            (list(callers), mode, mode, list(dangerous)),
        )
        return tuple((str(row[0]), str(row[1])) for row in cursor.fetchall())


def _check_reachability(
    connection: psycopg.Connection[Any],
    asset: dict[str, object],
    report: _ReportBuilder,
) -> None:
    """SET と USAGE の推移閉包を別々に危険終点と交差する。"""
    callers = _caller_role_ids(asset)
    dangerous = _dangerous_role_ids(connection, asset)
    for mode in ("SET", "USAGE"):
        report.compare(
            f"CATALOG:REACHABILITY:{mode}",
            (),
            _reachable_dangerous_roles(connection, callers, dangerous, mode),
        )


def _acl_rows(
    connection: psycopg.Connection[Any],
    query: LiteralString,
    parameters: tuple[object, ...],
) -> tuple[tuple[str, str, bool], ...]:
    """ACL 展開クエリの 3 列を共通形式へ正規化する。"""
    with connection.cursor() as cursor:
        cursor.execute(query, parameters)
        return tuple(
            (str(row[0]), str(row[1]).upper(), bool(row[2]))
            for row in cursor.fetchall()
        )


def _expected_object_acl(
    asset: dict[str, object], object_kind: str, object_id: str
) -> tuple[tuple[str, str, bool], ...]:
    """ACL expectation から object ごとの期待集合を作る。"""
    entries: list[tuple[str, str, bool]] = []
    for row in _rows(asset, "acl_expectations"):
        if row.get("object_kind") != object_kind or row.get("object_id") != object_id:
            continue
        grantee = _text(row.get("grantee_role_id"), "acl.grantee_role_id")
        grant_option = row.get("grant_option")
        if not isinstance(grant_option, bool):
            raise CatalogCheckError("acl.grant_optionはbooleanでなければならない")
        entries.extend(
            (grantee, privilege.upper(), grant_option)
            for privilege in _strings(row.get("privilege_ids"), "acl.privilege_ids")
        )
    return tuple(sorted(entries))


def _check_acl(
    connection: psycopg.Connection[Any],
    asset: dict[str, object],
    statements: dict[tuple[str, str], DDLStatement],
    report: _ReportBuilder,
) -> None:
    """表・列・schema・routine・default ACL を exact 照合する。"""
    public_entries: list[tuple[str, str]] = []
    for table in _rows(asset, "tables"):
        table_id = _text(table.get("table_id"), "tables.table_id")
        schema_id = _text(table.get("schema_id"), "tables.schema_id")
        actual = _acl_rows(
            connection,
            """
            SELECT COALESCE(grantee.rolname, 'PUBLIC'),
                   privilege.privilege_type,
                   privilege.is_grantable
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            CROSS JOIN LATERAL pg_catalog.aclexplode(relation.relacl) AS privilege
            LEFT JOIN pg_catalog.pg_roles AS grantee
              ON grantee.oid = privilege.grantee
            WHERE namespace.nspname = %s
              AND relation.relname = %s
              AND privilege.grantee <> relation.relowner
            ORDER BY 1, 2, 3
            """,
            (schema_id, table_id),
        )
        public_entries.extend(
            (f"table:{schema_id}.{table_id}", privilege)
            for grantee, privilege, _ in actual
            if grantee == "PUBLIC"
        )
        report.compare(
            f"CATALOG:ACL:TABLE:{table_id}",
            _expected_object_acl(asset, "table", table_id),
            actual,
        )

    for schema in _rows(asset, "schemas"):
        schema_id = _text(schema.get("schema_id"), "schemas.schema_id")
        expected = tuple(
            sorted(
                [
                    (role_id, "USAGE", False)
                    for role_id in _strings(
                        schema.get("usage_role_ids"), "schemas.usage_role_ids"
                    )
                ]
                + [
                    (role_id, "CREATE", False)
                    for role_id in _strings(
                        schema.get("create_role_ids"), "schemas.create_role_ids"
                    )
                ]
            )
        )
        actual = _acl_rows(
            connection,
            """
            SELECT COALESCE(grantee.rolname, 'PUBLIC'),
                   privilege.privilege_type,
                   privilege.is_grantable
            FROM pg_catalog.pg_namespace AS namespace
            CROSS JOIN LATERAL pg_catalog.aclexplode(namespace.nspacl) AS privilege
            LEFT JOIN pg_catalog.pg_roles AS grantee
              ON grantee.oid = privilege.grantee
            WHERE namespace.nspname = %s
              AND privilege.grantee <> namespace.nspowner
            ORDER BY 1, 2, 3
            """,
            (schema_id,),
        )
        public_entries.extend(
            (f"schema:{schema_id}", privilege)
            for grantee, privilege, _ in actual
            if grantee == "PUBLIC"
        )
        report.compare(f"CATALOG:ACL:SCHEMA:{schema_id}", expected, actual)

    function_rows = {
        _text(row.get("function_id"), "functions.function_id"): row
        for row in _rows(asset, "functions")
    }
    for function_id, function in function_rows.items():
        schema_id = _text(function.get("schema_id"), "functions.schema_id")
        statement = statements.get(("function", function_id))
        if statement is None:
            raise CatalogCheckError(f"function bodyがない: {function_id}")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_catalog.to_regprocedure(%s)::oid",
                (_function_regprocedure(statement),),
            )
            expected_oid_row = cursor.fetchone()
            expected_oid = (
                int(expected_oid_row[0])
                if expected_oid_row is not None and expected_oid_row[0] is not None
                else None
            )
            cursor.execute(
                """
                SELECT routine.oid
                FROM pg_catalog.pg_proc AS routine
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = routine.pronamespace
                WHERE namespace.nspname = %s
                  AND routine.proname = %s
                ORDER BY pg_catalog.pg_get_function_identity_arguments(routine.oid)
                """,
                (schema_id, function_id),
            )
            routine_oids = tuple(int(row[0]) for row in cursor.fetchall())
        actual_by_oid = tuple(
            (
                routine_oid,
                _acl_rows(
                    connection,
                    """
                    SELECT COALESCE(grantee.rolname, 'PUBLIC'),
                           privilege.privilege_type,
                           privilege.is_grantable
                    FROM pg_catalog.pg_proc AS routine
                    CROSS JOIN LATERAL
                         pg_catalog.aclexplode(routine.proacl) AS privilege
                    LEFT JOIN pg_catalog.pg_roles AS grantee
                      ON grantee.oid = privilege.grantee
                    WHERE routine.oid = %s
                      AND privilege.grantee <> routine.proowner
                    ORDER BY 1, 2, 3
                    """,
                    (routine_oid,),
                ),
            )
            for routine_oid in routine_oids
        )
        public_entries.extend(
            (f"function:{schema_id}.{function_id}", privilege)
            for _, acl in actual_by_oid
            for grantee, privilege, _ in acl
            if grantee == "PUBLIC"
        )
        report.compare(
            f"CATALOG:ACL:FUNCTION:{function_id}",
            ((expected_oid, _expected_object_acl(asset, "function", function_id)),),
            actual_by_oid,
        )

    column_expectations = _rows(asset, "column_acl_expectations")
    for expectation in column_expectations:
        expectation_id = _text(
            expectation.get("expectation_id"), "column_acl_expectations.expectation_id"
        )
        table_ids = _strings(
            expectation.get("table_ids"), "column_acl_expectations.table_ids"
        )
        declared_grantees = _strings(
            expectation.get("grantee_role_ids"),
            "column_acl_expectations.grantee_role_ids",
        )
        asset_role_ids = {
            _text(row.get("role_id"), "roles.role_id") for row in _rows(asset, "roles")
        }
        if set(declared_grantees) != asset_role_ids:
            raise CatalogCheckError(
                "column ACLのgrantee_role_idsが資産role集合と一致しない"
            )
        table_schemas = {
            _text(row.get("schema_id"), "tables.schema_id")
            for row in _rows(asset, "tables")
            if row.get("table_id") in table_ids
        }
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT namespace.nspname,
                       relation.relname,
                       attribute.attname,
                       COALESCE(grantee.rolname, 'PUBLIC'),
                       privilege.privilege_type,
                       privilege.is_grantable
                FROM pg_catalog.pg_attribute AS attribute
                JOIN pg_catalog.pg_class AS relation
                  ON relation.oid = attribute.attrelid
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                CROSS JOIN LATERAL pg_catalog.aclexplode(attribute.attacl) AS privilege
                LEFT JOIN pg_catalog.pg_roles AS grantee
                  ON grantee.oid = privilege.grantee
                WHERE relation.relname = ANY(%s)
                  AND namespace.nspname = ANY(%s)
                ORDER BY 1, 2, attribute.attnum, 4, 5, 6
                """,
                (list(table_ids), sorted(table_schemas)),
            )
            actual = tuple(tuple(row) for row in cursor.fetchall())
        expected_entries = expectation.get("expected_entries")
        if not isinstance(expected_entries, list):
            raise CatalogCheckError(
                "column ACL expected_entriesはarrayでなければならない"
            )
        report.compare(
            f"CATALOG:ACL:COLUMN:{expectation_id}",
            tuple(expected_entries),
            actual,
        )
        public_entries.extend(
            (f"column:{row[0]}.{row[1]}.{row[2]}", str(row[4]))
            for row in actual
            if row[3] == "PUBLIC"
        )

    role_ids = tuple(
        _text(row.get("role_id"), "roles.role_id") for row in _rows(asset, "roles")
    )
    schema_ids = tuple(
        _text(row.get("schema_id"), "schemas.schema_id")
        for row in _rows(asset, "schemas")
    )
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
            JOIN pg_catalog.pg_roles AS owner ON owner.oid = defaults.defaclrole
            LEFT JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = defaults.defaclnamespace
            CROSS JOIN LATERAL pg_catalog.aclexplode(defaults.defaclacl) AS privilege
            LEFT JOIN pg_catalog.pg_roles AS grantee
              ON grantee.oid = privilege.grantee
            WHERE owner.rolname = ANY(%s)
               OR namespace.nspname = ANY(%s)
            ORDER BY 1, 2, 3, 4, 5, 6
            """,
            (list(role_ids), list(schema_ids)),
        )
        default_acl = tuple(tuple(row) for row in cursor.fetchall())
    report.compare("CATALOG:ACL:DEFAULT", (), default_acl)
    public_entries.extend(
        (f"default:{row[0]}:{row[1]}:{row[2]}", str(row[4]))
        for row in default_acl
        if row[3] == "PUBLIC"
    )
    report.compare("CATALOG:ACL:PUBLIC", (), tuple(sorted(public_entries)))


def _check_provisioner_completion(
    connection: psycopg.Connection[Any],
    asset: dict[str, object],
    report: _ReportBuilder,
) -> None:
    """資産記載の SET・USAGE 完了時述語を全 owner へ適用する。"""
    claim = asset.get("provisioning_claim")
    if not isinstance(claim, dict):
        raise CatalogCheckError("provisioning_claimはobjectでなければならない")
    raw_expectations = claim.get("completion_catalog_expectations")
    if not isinstance(raw_expectations, list) or not all(
        isinstance(row, dict) for row in raw_expectations
    ):
        raise CatalogCheckError("completion_catalog_expectationsはobject配列でない")
    provisioners = [
        row
        for row in _rows(asset, "roles")
        if row.get("role_kind") == "external_provisioner"
    ]
    if len(provisioners) != 1:
        raise CatalogCheckError("external_provisionerを一意に導出できない")
    provisioner = _text(provisioners[0].get("role_id"), "roles.role_id")
    owners = tuple(
        dict.fromkeys(
            _text(row.get("owner_role_id"), "functions.owner_role_id")
            for row in _rows(asset, "functions")
        )
    )
    for expectation in raw_expectations:
        if not isinstance(expectation, dict):
            continue
        check_id = _text(expectation.get("catalog_check_id"), "catalog_check_id")
        predicate = _text(
            expectation.get("inspection_predicate"), "inspection_predicate"
        )
        modes = [mode for mode in ("SET", "USAGE") if f"'{mode}'" in predicate]
        if len(modes) != 1 or "= false" not in predicate:
            raise CatalogCheckError(f"未対応の完了時述語: {check_id}")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT owner.rolname,
                       pg_catalog.pg_has_role(provisioner.oid, owner.oid, %s)
                FROM pg_catalog.pg_roles AS provisioner
                CROSS JOIN pg_catalog.pg_roles AS owner
                WHERE provisioner.rolname = %s
                  AND owner.rolname = ANY(%s)
                ORDER BY owner.rolname
                """,
                (modes[0], provisioner, list(owners)),
            )
            actual = tuple((str(row[0]), bool(row[1])) for row in cursor.fetchall())
        report.compare(
            check_id,
            tuple((owner, False) for owner in sorted(owners)),
            actual,
        )


def _check_owned_objects(
    connection: psycopg.Connection[Any],
    asset: dict[str, object],
    statements: dict[tuple[str, str], DDLStatement],
    report: _ReportBuilder,
) -> None:
    """BYPASSRLS owner の object と SECURITY DEFINER 関数を exact 照合する。"""
    bypass_roles = tuple(
        _text(row.get("role_id"), "roles.role_id")
        for row in _rows(asset, "roles")
        if row.get("bypass_rls") is True
    )
    expected_addresses: list[tuple[int, int, int, str]] = []
    for schema in _rows(asset, "schemas"):
        owner = _text(schema.get("owner_role_id"), "schemas.owner_role_id")
        if owner in bypass_roles:
            schema_id = _text(schema.get("schema_id"), "schemas.schema_id")
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 'pg_catalog.pg_namespace'::regclass::oid,
                           namespace.oid,
                           0,
                           %s
                    FROM pg_catalog.pg_namespace AS namespace
                    WHERE namespace.nspname = %s
                    """,
                    (owner, schema_id),
                )
                expected_addresses.extend(
                    (int(row[0]), int(row[1]), int(row[2]), str(row[3]))
                    for row in cursor.fetchall()
                )
    table_schemas = {
        _text(row.get("table_id"), "tables.table_id"): _text(
            row.get("schema_id"), "tables.schema_id"
        )
        for row in _rows(asset, "tables")
    }
    for table in _rows(asset, "tables"):
        owner = _text(table.get("owner_role_id"), "tables.owner_role_id")
        if owner in bypass_roles:
            table_id = _text(table.get("table_id"), "tables.table_id")
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 'pg_catalog.pg_class'::regclass::oid,
                           relation.oid,
                           0,
                           %s
                    FROM pg_catalog.pg_class AS relation
                    JOIN pg_catalog.pg_namespace AS namespace
                      ON namespace.oid = relation.relnamespace
                    WHERE namespace.nspname = %s
                      AND relation.relname = %s
                    """,
                    (owner, table_schemas[table_id], table_id),
                )
                expected_addresses.extend(
                    (int(row[0]), int(row[1]), int(row[2]), str(row[3]))
                    for row in cursor.fetchall()
                )
    for function in _rows(asset, "functions"):
        owner = _text(function.get("owner_role_id"), "functions.owner_role_id")
        if owner in bypass_roles:
            function_id = _text(function.get("function_id"), "functions.function_id")
            statement = statements.get(("function", function_id))
            if statement is None:
                raise CatalogCheckError(f"function bodyがない: {function_id}")
            regprocedure = _function_regprocedure(statement)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 'pg_catalog.pg_proc'::regclass::oid,
                           pg_catalog.to_regprocedure(%s)::oid,
                           0,
                           %s
                    WHERE pg_catalog.to_regprocedure(%s) IS NOT NULL
                    """,
                    (regprocedure, owner, regprocedure),
                )
                expected_addresses.extend(
                    (int(row[0]), int(row[1]), int(row[2]), str(row[3]))
                    for row in cursor.fetchall()
                )
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT dependency.classid,
                   dependency.objid,
                   dependency.objsubid,
                   owner.rolname
            FROM pg_catalog.pg_shdepend AS dependency
            JOIN pg_catalog.pg_roles AS owner
              ON owner.oid = dependency.refobjid
            WHERE dependency.refclassid = 'pg_catalog.pg_authid'::regclass
              AND dependency.deptype = 'o'
              AND owner.rolname = ANY(%s)
              AND dependency.dbid IN (
                  0,
                  (
                      SELECT database.oid
                      FROM pg_catalog.pg_database AS database
                      WHERE database.datname = pg_catalog.current_database()
                  )
              )
            ORDER BY 1, 2, 3, 4
            """,
            (list(bypass_roles),),
        )
        actual_addresses = tuple(
            (int(row[0]), int(row[1]), int(row[2]), str(row[3]))
            for row in cursor.fetchall()
        )
    report.compare(
        "CATALOG:OWNED-OBJECTS:BYPASSRLS",
        tuple(sorted(expected_addresses)),
        actual_addresses,
    )

    expected_definers = tuple(
        sorted(
            (
                _text(row.get("schema_id"), "functions.schema_id"),
                _text(row.get("function_id"), "functions.function_id"),
            )
            for row in _rows(asset, "functions")
            if row.get("security_mode") == "definer"
        )
    )
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT namespace.nspname, routine.proname
            FROM pg_catalog.pg_proc AS routine
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = routine.pronamespace
            WHERE routine.prosecdef
              AND namespace.nspname !~ '^pg_'
              AND namespace.nspname <> 'information_schema'
            ORDER BY 1, 2, pg_catalog.pg_get_function_identity_arguments(routine.oid)
            """
        )
        actual_definers = tuple((str(row[0]), str(row[1])) for row in cursor.fetchall())
    report.compare(
        "CATALOG:OWNED-OBJECTS:SECURITY-DEFINER",
        expected_definers,
        actual_definers,
    )


def inspect_authz_catalog(
    connection: psycopg.Connection[Any],
    root: Path,
    *,
    reference_connection: psycopg.Connection[Any],
) -> CatalogReport:
    """実 PostgreSQL カタログを資産期待値と照合する。

    ステップ 3 の生成器を入口にするため、ステップ 2 の公開検査器
    ``validate_repository`` とその ``git_blob_digest`` による現ファイル・
    ``source_commit`` の二段照合を通過した body だけを期待値へ使う。

    Args:
        connection: 検査対象クラスタへのカタログ読取可能な接続。
        root: ``contracts/authz`` を含むリポジトリルート。
        reference_connection: 同じクラスタの別 database に封印済み DDL だけを
            適用した参照接続。

    Returns:
        実施した検査 ID と全不一致を保持するレポート。

    Raises:
        CatalogCheckError: 資産不正、body 封印違反、またはカタログ観測失敗。
    """
    root = root.resolve()
    asset = _read_json_object(root / DDL_ELEMENTS_PATH, "ddl-elements")
    report = _ReportBuilder()
    try:
        functions = _rows(asset, "functions")
        statements, reference_definitions = _sealed_reference_function_definitions(
            root,
            connection,
            reference_connection,
            functions,
        )
        _check_policies(connection, asset, statements, report)
        _check_functions(
            connection,
            asset,
            statements,
            reference_definitions,
            report,
        )
        _check_reachability(connection, asset, report)
        _check_acl(connection, asset, statements, report)
        _check_provisioner_completion(connection, asset, report)
        _check_owned_objects(connection, asset, statements, report)
        connection.rollback()
        reference_connection.rollback()
    except CatalogCheckError:
        connection.rollback()
        reference_connection.rollback()
        raise
    except (psycopg.Error, ValueError, TypeError) as error:
        connection.rollback()
        reference_connection.rollback()
        raise CatalogCheckError(f"PostgreSQLカタログを観測できない: {error}") from error
    return report.build()
