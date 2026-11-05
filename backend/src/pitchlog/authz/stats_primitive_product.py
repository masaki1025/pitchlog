"""成績native4関数・列ACL・tenant policyの閉publisher候補。"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.dialects import postgresql

from pitchlog.authz.function_result_type import pg_result_type
from pitchlog.authz.stats_primitive_sql import candidate_function_bodies
from pitchlog.db.game_state.stats import (
    StatsFactVersion,
    StatsPrimitiveFact,
    StatsPrimitiveSource,
)
from pitchlog.domaingen.core import _canonical_hash

OWNER = "pitchlog_sync_right_fn_owner"
APP = "pitchlog_app"
_FUNCTIONS = {
    "save_primitive_source": "save_source",
    "open_primitive_snapshot": "open_snapshot",
    "read_play_export_primitives": "read_page",
    "read_primitive_totals": "read_totals",
}
# 採用済み54列の型/nullableだけを固定し、別の表定義を作らない。
_COLUMN_SCHEMAS = {
    "stats_fact_versions": (
        "sha256:f4a10c6dfa1403d0ef18b89ac6c6c2fac10d29f55866585cf37ebe80f31fe293"
    ),
    "stats_primitive_sources": (
        "sha256:67daa8ea99110b28fe59eef3289706dfbe6f80801f5cf69d5350637f5526bb4b"
    ),
    "stats_primitive_facts": (
        "sha256:2e81f4cab974a6f4f742c2c535b62a322f6241867ec12b20613660f21ed82c98"
    ),
}
_VERSION_UPDATES = frozenset(
    {
        "is_current",
        "invalidated_at",
        "revision",
        "source_set_sha256",
        "source_count",
        "computed_metric_keys",
        "last_generation",
        "last_d1",
        "last_d2",
        "updated_at",
    }
)
_PREDICATE = (
    "tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid"
    " AND session_user = 'pitchlog_app'"
)


def _relations() -> dict[str, list[str]]:
    """実modelの列型/nullableを採用集合と照合し、列名だけを使用する。"""
    result = {}
    for model in (StatsFactVersion, StatsPrimitiveSource, StatsPrimitiveFact):
        table = model.__table__
        columns = {
            str(column.name): {
                "type": str(column.type.compile(dialect=postgresql.dialect())),
                "nullable": column.nullable,
            }
            for column in table.c
        }
        if table.schema != "sync_fence" or (
            _canonical_hash(columns) != _COLUMN_SCHEMAS[table.name]
        ):
            raise ValueError("成績の実表列/型/nullableが採用集合と不一致")
        # ORM識別子quoted_nameをJSONのplain strへ閉じる。利用者入力は変換しない。
        result[str(table.name)] = list(columns)
    if StatsFactVersion.immutability.conditional_update_columns != _VERSION_UPDATES:
        raise ValueError("成績版の更新可能列が採用集合と不一致")
    return result


def candidate_declarations() -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """採用済み4関数/70列ACL/10policyだけを描画し、適用しない。"""
    declarations: dict[str, list[dict[str, Any]]] = {
        "functions": [],
        "policies": [],
        "column_acl_expectations": [],
    }
    bodies: dict[str, str] = {}
    sql_bodies = candidate_function_bodies()
    if set(sql_bodies) != set(_FUNCTIONS):
        raise ValueError("成績関数集合が閉じていません")
    for name in _FUNCTIONS:
        body = sql_bodies[name]
        match = re.match(
            r"CREATE FUNCTION stats_api\.(\w+)\((.*?)\)\n"
            r"RETURNS TABLE\((.*?)\) LANGUAGE",
            body,
            re.S,
        )
        if match is None or match[1] != name:
            raise ValueError("成績の関数署名を特定できません")
        args = ", ".join(
            " ".join(arg.strip().split()[1:]) for arg in match[2].split(",")
        )
        key = f"FUNCTION:stats_api:{name}({args})"
        declarations["functions"].append(
            {
                "function_id": key,
                "schema_name": "stats_api",
                "function_name": name,
                "identity_args": args,
                "function_kind": "definer",
                "owner_role_id": OWNER,
                "language": "plpgsql",
                "returns": "TABLE(" + match[3] + ")",
                "security_mode": "definer",
                "volatility": "volatile",
                "search_path": ["pg_catalog", "pg_temp"],
                "acl_expectations": [
                    {"grantee": APP, "privilege": "EXECUTE", "grantable": False}
                ],
                "revoked_acl_expectations": [
                    {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
                ],
            }
        )
        bodies["function|" + key] = body
    for table, columns in _relations().items():
        for column in columns:
            privileges = ["SELECT", "INSERT"]
            if table == "stats_fact_versions" and column in _VERSION_UPDATES:
                privileges.append("UPDATE")
            _add_column(declarations, bodies, "sync_fence", table, column, privileges)
        for command in ["SELECT", "INSERT"] + (
            ["UPDATE"] if table == "stats_fact_versions" else []
        ):
            name = "stats_primitives_" + command.lower()
            scoped = _PREDICATE + (
                " AND completion_state='current_open'"
                if table == "stats_fact_versions" and command != "SELECT"
                else ""
            )
            if table != "stats_fact_versions" and command == "INSERT":
                scoped += (
                    " AND EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions v WHERE "
                    "v.tenant_id="
                    + table
                    + ".tenant_id AND v.game_id="
                    + table
                    + ".game_id "
                    "AND v.id="
                    + table
                    + ".fact_version_id AND v.is_current AND v.invalidated_at IS NULL "
                    "AND v.completion_state='current_open')"
                )
            _add_policy(
                declarations, bodies, "sync_fence", table, name, command, scoped
            )
    for table, columns in {
        "players": ["tenant_id", "id"],
        "games": ["tenant_id", "id", "status", "hidden_at", "trashed_at"],
        "event_slots": [
            "tenant_id",
            "game_id",
            "generation",
            "d1",
            "confirmed_version",
        ],
    }.items():
        for column in columns:
            _add_column(declarations, bodies, "public", table, column, ["SELECT"])
        _add_policy(
            declarations,
            bodies,
            "public",
            table,
            "stats_primitives_select",
            "SELECT",
            _PREDICATE + " AND current_user = '" + OWNER + "'",
        )
    for schema, table in [
        ("public", "operation_events"),
        ("public", "play_rows"),
        ("public", "idempotency_ledger"),
        ("sync_fence", "ordinary_pitch_checkpoints"),
    ]:
        _add_column(declarations, bodies, schema, table, "xmin", ["SELECT"])
    if [
        len(declarations[s])
        for s in ("functions", "column_acl_expectations", "policies")
    ] != [4, 70, 10] or len(bodies) != 84:
        raise ValueError("成績publisherの閉集合が不一致")
    return declarations, bodies


def _add_column(declarations, bodies, schema, table, column, privileges):
    """閉じたcallerの列権限をgrant optionなしで描画する。"""
    if privileges not in (
        ["SELECT"],
        ["SELECT", "INSERT"],
        ["SELECT", "INSERT", "UPDATE"],
    ):
        raise ValueError("成績の列権限が未登録です")
    key = f"COLUMN-ACL:{schema}:{table}:{column}:{OWNER}"
    declarations["column_acl_expectations"].append(
        {
            "expectation_id": key,
            "object_kind": "column",
            "object_schema": schema,
            "object_id": table,
            "column_id": column,
            "grantee_role_id": OWNER,
            "privilege_ids": privileges,
            "grant_option": False,
        }
    )
    separator = "," if schema == "sync_fence" and column != "xmin" else ", "
    bodies["column_acl_expectation|" + key] = (
        "GRANT "
        + separator.join(p + " (" + column + ")" for p in privileges)
        + " ON "
        + schema
        + "."
        + table
        + " TO "
        + OWNER
        + ";\n"
    )


def _add_policy(declarations, bodies, schema, table, name, command, predicate):
    """同tenantの有限SELECT/INSERT/UPDATEだけを受ける。"""
    if command not in ("SELECT", "INSERT", "UPDATE"):
        raise ValueError("成績policyのcommandが未登録です")
    key = f"POLICY:{table}:{name}"
    using = predicate if command != "INSERT" else None
    check = predicate if command != "SELECT" else None
    declarations["policies"].append(
        {
            "policy_id": key,
            "table_id": table,
            "profile": "function_only",
            "policy_name": name,
            "command": command,
            "policy_mode": "permissive",
            "role_ids": [OWNER],
            "using_predicate_id": None,
            "using_column": None,
            "using_expression": using,
            "with_check_predicate_id": None,
            "with_check_column": None,
            "with_check_expression": check,
        }
    )
    bodies["policy|" + key] = (
        "CREATE POLICY "
        + name
        + " ON "
        + schema
        + "."
        + table
        + " AS PERMISSIVE FOR "
        + command
        + " TO "
        + OWNER
        + (" USING (" + using + ")" if using else "")
        + (" WITH CHECK (" + check + ")" if check else "")
        + ";\n"
    )


def candidate_schema() -> dict[str, Any]:
    """新schemaの所有/USAGEだけを既producer形式で供給する。"""
    return {
        "schema_id": "stats_api",
        "schema_name": "stats_api",
        "creation": "product_ddl",
        "owner": "pitchlog_owner",
        "ownership_path": "direct",
        "acl_expectations": [
            {"grantee": APP, "privilege": "USAGE", "grantable": False},
            {"grantee": OWNER, "privilege": "USAGE", "grantable": False},
        ],
        "revoked_acl_expectations": [
            {"grantee": role, "privilege": privilege, "grantable": False}
            for role, privilege in [
                ("PUBLIC", "USAGE"),
                ("PUBLIC", "CREATE"),
                (APP, "CREATE"),
                (OWNER, "CREATE"),
            ]
        ],
    }


def candidate_schema_body() -> str:
    """既schemaのownerを修復せず照合し、新schemaの最小USAGEだけを供給する。"""
    return (
        "DO $stats_schema$\nBEGIN\n"
        " IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_namespace n\n"
        "  JOIN pg_catalog.pg_roles r ON r.oid=n.nspowner\n"
        "  WHERE n.nspname='stats_api' AND r.rolname='pitchlog_owner') THEN\n"
        "  IF EXISTS(SELECT 1 FROM pg_catalog.pg_namespace WHERE "
        "nspname='stats_api') THEN\n"
        "   RAISE EXCEPTION 'stats schema owner collision';\n"
        "  END IF;\n"
        "  CREATE SCHEMA stats_api AUTHORIZATION pitchlog_owner;\n"
        " END IF;\nEND;$stats_schema$;\n"
        "REVOKE ALL ON SCHEMA stats_api FROM PUBLIC;\n"
        "REVOKE CREATE ON SCHEMA stats_api FROM pitchlog_app,"
        "pitchlog_sync_right_fn_owner;\n"
        "GRANT USAGE ON SCHEMA stats_api TO pitchlog_app,"
        "pitchlog_sync_right_fn_owner;\n"
    )


def declaration(section: str, key: str) -> dict[str, Any] | None:
    """正式installerが既guardへ渡す閉じた宣言。未知IDを発行しない。"""
    declarations, _ = candidate_declarations()
    identity = {
        "functions": "function_id",
        "policies": "policy_id",
        "column_acl_expectations": "expectation_id",
    }.get(section)
    if identity is None:
        return None
    return next((row for row in declarations[section] if row[identity] == key), None)


def body(kind: str, key: str) -> str | None:
    """既guardが照合するcanonical本文。適用や再封印はしない。"""
    return candidate_declarations()[1].get(kind + "|" + key)


def function_details() -> tuple[tuple[object, ...], ...]:
    """既reapply guardに渡す全属性を同じ本文・既型codecから作る。"""
    declarations, bodies = candidate_declarations()
    result = []
    for row in declarations["functions"]:
        sql = bodies["function|" + row["function_id"]]
        delimiter = re.search(r"\bAS\s+(\$[A-Za-z0-9_]*\$)", sql)
        if delimiter is None or len(parts := sql.split(delimiter[1])) != 3:
            raise ValueError("成績関数本文が一意でありません")
        result.append(
            (
                row["schema_name"],
                row["function_name"],
                row["identity_args"],
                row["owner_role_id"],
                True,
                row["language"],
                pg_result_type(row["returns"]),
                "v",
                ("search_path=pg_catalog, pg_temp",),
                parts[1].strip(),
            )
        )
    return tuple(sorted(result))


def operation_candidates() -> list[dict[str, Any]]:
    """nonce/RRROのroot接合を要する既4operationだけを宣言する。"""
    declarations, bodies = candidate_declarations()
    result = []
    for row in declarations["functions"]:
        name = row["function_name"]
        sql = bodies["function|" + row["function_id"]]
        match = re.match(r"CREATE FUNCTION stats_api\.\w+\((.*?)\)\n", sql, re.S)
        if match is None:
            raise ValueError("成績operationの引数が不一致")
        parameters = [part.strip().split() for part in match[1].split(",")]
        if any(
            len(part) != 2
            or part[1] not in {"uuid", "text", "bigint", "jsonb", "bytea", "integer"}
            or re.fullmatch(r"p_[a-z][a-z0-9_]*", part[0]) is None
            for part in parameters
        ):
            raise ValueError("成績operationの型/参照が未登録です")
        operation = _FUNCTIONS[name]
        result.append(
            {
                "operation_id": "STATS_PRIMITIVES:" + operation,
                "capability_id": "CAP:stats_primitives:"
                + ("save_source" if operation == "save_source" else "read"),
                "function_id": row["function_id"],
                "parameters": [
                    {"name": part[0], "sql_type": part[1]} for part in parameters
                ],
                "qualification": "root same-frame evaluation+nonce injection"
                if operation == "save_source"
                else (
                    "root RRRO marker + opaque same-handle receipt for Page/Totals; "
                    "SQL snapshot is supplementary"
                ),
            }
        )
    return result


def function_application_body(function_id: str) -> str | None:
    """生SQLを保持したまま、既採用installerの所有/ACL footerを付ける。"""
    declarations, bodies = candidate_declarations()
    row = next(
        (row for row in declarations["functions"] if row["function_id"] == function_id),
        None,
    )
    if row is None:
        return None
    return _application_body(row, bodies["function|" + function_id])


def _application_body(row: dict[str, Any], sql: str) -> str:
    """既採用installerのfooterだけを付け、raw本文を変えない。"""
    identity = f"stats_api.{row['function_name']}({row['identity_args']})"
    return (
        sql + f"\nALTER FUNCTION {identity} OWNER TO {OWNER};\n"
        f"REVOKE ALL ON FUNCTION {identity} FROM PUBLIC,{APP};\n"
        f"GRANT EXECUTE ON FUNCTION {identity} TO {APP};\n"
    )


def candidate_install_sql() -> str:
    """既installer全byteを再現し、実DBへの適用は呼出側へ残す。"""
    declarations, bodies = candidate_declarations()
    return "\n".join(
        _application_body(row, bodies["function|" + row["function_id"]])
        for row in declarations["functions"]
    )


def candidate_table_profile() -> list[dict[str, Any]]:
    """既migrationと同じ私有3表/所有/RLSを登録側へ明示する。"""
    return [
        {
            "table_id": table,
            "schema_name": "sync_fence",
            "owner": "pitchlog_owner",
            "enable_row_level_security": True,
            "force_row_level_security": True,
        }
        for table in _relations()
    ]


def candidate_table_declarations() -> tuple[list[dict[str, Any]], dict[str, str]]:
    """84採用bodyを変えず、別途必要な3表RLS宣言だけを供給する。"""
    rows = []
    bodies = {}
    for profile in candidate_table_profile():
        row = {key: value for key, value in profile.items() if key != "owner"}
        rows.append(row)
        table = row["table_id"]
        bodies["table|" + table] = (
            f"ALTER TABLE sync_fence.{table} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE sync_fence.{table} FORCE ROW LEVEL SECURITY;\n"
            f"REVOKE ALL ON TABLE sync_fence.{table} FROM PUBLIC,pitchlog_app;\n"
        )
    return rows, bodies


def connection_declarations() -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """採用4関数を保持し前値1/schema/私有3表だけをcanonical集合へ供給する。"""
    from pitchlog.authz import stats_primitive_write_state as writer

    declarations, bodies = candidate_declarations()
    for row in declarations["functions"]:
        key = "function|" + row["function_id"]
        bodies[key] = _application_body(row, bodies[key])
    extra, extra_bodies = writer.candidate_declarations()
    if len(extra["functions"]) != 1 or set(extra_bodies) != {
        "function|" + writer.FUNCTION_ID
    }:
        raise ValueError("成績writer前値の追加集合が不一致")
    declarations["functions"].extend(extra["functions"])
    # 同じ候補内で既に取得した原本を使い、Save guardを重複生成しない。
    bodies["function|" + writer.FUNCTION_ID] = _application_body(
        extra["functions"][0], extra_bodies["function|" + writer.FUNCTION_ID]
    )
    declarations["schemas"] = [candidate_schema()]
    bodies["schema|stats_api"] = candidate_schema_body()
    tables, table_bodies = candidate_table_declarations()
    declarations["tables"] = tables
    bodies.update(table_bodies)
    if len(declarations["functions"]) != 5 or len(tables) != 3:
        raise ValueError("成績接合の固定関数/表集合が不一致")
    return declarations, bodies
