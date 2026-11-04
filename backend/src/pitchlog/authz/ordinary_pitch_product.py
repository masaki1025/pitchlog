"""通常投球private原本の有限profile候補。適用は正式資産の受理後に行う。

SQL本文はwriter/bridge/資格の各単一定義から取得する。appへprivate表権限を
付与せず、fnownerにも物理削除・TRUNCATE・所有権・BYPASSRLSを与えない。
"""

import copy
import re

from pitchlog.authz.ordinary_order_sql import candidate_order_function_bodies
from pitchlog.authz.ordinary_pitch_write_stamp import candidate_function_bodies
from pitchlog.authz.ordinary_prefix_sql import candidate_read_function_bodies
from pitchlog.authz.sync_right_sql import render_ordinary_stamped_function_sql

_OWNER = "pitchlog_sync_right_fn_owner"
_TABLES = (
    "ordinary_pitch_checkpoints",
    "ordinary_pitch_write_admissions",
    "ordinary_pitch_history",
)
_FUNCTIONS = {
    "read_ordinary_order_summary": ("uuid, uuid", "TABLE(record_json text)"),
    "bind_ordinary_device": (
        "uuid, uuid, uuid, bytea, uuid, uuid, bytea",
        "TABLE(device_matches boolean)",
    ),
    "check_ordinary_right": (
        "uuid, uuid, uuid, bytea, uuid, uuid, bigint, bigint, bytea",
        "TABLE(recovery_matches boolean, right_matches boolean)",
    ),
    "prepare_ordinary_projection": (
        "uuid, uuid, uuid, bytea, uuid, uuid, text",
        "TABLE(prepared boolean)",
    ),
    "consume_ordinary_projection": ("jsonb", "void"),
    "read_ordinary_checkpoint": ("uuid, uuid, bigint", "TABLE(record_json text)"),
    "lock_ordinary_checkpoint": (
        "uuid, uuid, uuid, bytea, uuid, uuid, bigint",
        "TABLE(record_json text)",
    ),
    "read_ordinary_history_page": (
        (
            "uuid, uuid, bigint, bigint, uuid, bigint, bigint, "
            "bigint, bigint, uuid, integer"
        ),
        "TABLE(record_json text)",
    ),
}


def _plain_identifiers(value):
    """SQLAlchemy quoted_nameを生成境界でplain strへ写し、型厳密比較は保つ。"""
    if isinstance(value, str):
        return str(value)
    if type(value) is dict:
        return {_plain_identifiers(k): _plain_identifiers(v) for k, v in value.items()}
    if type(value) is list:
        return [_plain_identifiers(item) for item in value]
    if type(value) is tuple:
        return tuple(_plain_identifiers(item) for item in value)
    return value


def candidate_profile():
    """現modelの必要列から権限候補を生成する。資格の成功証明ではない。"""
    from pitchlog.authz.sync_right_sql import _STAMP_COLS
    from pitchlog.db import all_models  # noqa: F401
    from pitchlog.db.base import Base
    from pitchlog.db.writer_binding.ordinary_models import (
        OrdinaryPitchCheckpoint,
        OrdinaryPitchHistory,
        OrdinaryPitchWriteAdmission,
    )

    tables = (
        OrdinaryPitchCheckpoint.__table__,
        OrdinaryPitchWriteAdmission.__table__,
        OrdinaryPitchHistory.__table__,
    )
    grants = []
    for table in tables:
        names = list(table.c.keys())
        # admission.xminのtop-level TX照合だけはsystem列のため表SELECTが必要。
        grants.append(
            (
                table.schema,
                table.name,
                "SELECT",
                None if table.name.endswith("admissions") else names,
            )
        )
        inserts = (
            _STAMP_COLS.split(",") + ["state"]
            if table.name.endswith("admissions")
            else names
        )
        grants.append((table.schema, table.name, "INSERT", inserts))
        if table is not OrdinaryPitchHistory.__table__:
            mutable = sorted(
                (
                    OrdinaryPitchWriteAdmission
                    if table.name.endswith("admissions")
                    else OrdinaryPitchCheckpoint
                ).immutability.conditional_update_columns
            )
            grants.append((table.schema, table.name, "UPDATE", mutable))
    # 有限JOINが返す実原本全列。SELECTのみで業務表を書ける権限を追加しない。
    for name in ("operation_events", "play_rows"):
        grants.append(
            ("public", name, "SELECT", list(Base.metadata.tables[name].c.keys()))
        )
    grants.append(
        (
            "public",
            "recording_generations",
            "SELECT",
            ["confirmed_watermark", "applied_prefix"],
        )
    )
    predicate = (
        "tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid"
        " AND session_user = 'pitchlog_app'"
    )
    policies = []
    for name in (*_TABLES, "play_rows"):
        schema = "sync_fence" if name in _TABLES else "public"
        commands = (
            ("SELECT", "INSERT")
            if name.endswith("history")
            else ("SELECT", "INSERT", "UPDATE")
        )
        if name == "play_rows":
            commands = ("SELECT",)
        for command in commands:
            policy_name = f"ordinary_pitch_{command.lower()}_{name}"
            policies.append(
                {
                    "policy_id": f"POLICY:{name}:{policy_name}",
                    "table_id": name,
                    "profile": "function_only",
                    "policy_name": policy_name,
                    "command": command,
                    "policy_mode": "permissive",
                    "role_ids": [_OWNER],
                    "using_predicate_id": None,
                    "using_column": None,
                    "using_expression": None if command == "INSERT" else predicate,
                    "with_check_predicate_id": None,
                    "with_check_column": None,
                    "with_check_expression": predicate
                    if command in {"INSERT", "UPDATE"}
                    else None,
                    "schema_name": schema,
                }
            )
    bodies = {
        **render_ordinary_stamped_function_sql(),
        **candidate_function_bodies(),
        **candidate_read_function_bodies(),
        **candidate_order_function_bodies(),
    }
    if bodies.keys() != _FUNCTIONS.keys():
        raise ValueError("通常投球関数候補の閉集合が不一致")
    return {
        "tables": [
            {
                "table_id": t.name,
                "schema_name": t.schema,
                "owner": "pitchlog_owner",
                "enable_row_level_security": True,
                "force_row_level_security": True,
            }
            for t in tables
        ],
        "functions": [
            {
                "function_id": f"FUNCTION:sync_right_api:{name}({identity})",
                "schema_name": "sync_right_api",
                "function_name": name,
                "identity_args": identity,
                "function_kind": "definer",
                "owner_role_id": _OWNER,
                "language": "plpgsql",
                "returns": returns,
                "security_mode": "definer",
                "volatility": "volatile",
                "search_path": ["pg_catalog", "pg_temp"],
                "acl_expectations": []
                if name == "consume_ordinary_projection"
                else [
                    {
                        "grantee": "pitchlog_app",
                        "privilege": "EXECUTE",
                        "grantable": False,
                    }
                ],
                "revoked_acl_expectations": [
                    {"grantee": role, "privilege": "EXECUTE", "grantable": False}
                    for role in (
                        ("PUBLIC", "pitchlog_app")
                        if name == "consume_ordinary_projection"
                        else ("PUBLIC",)
                    )
                ],
                "sql": bodies[name],
            }
            for name, (identity, returns) in _FUNCTIONS.items()
        ],
        "policies": policies,
        "grants": grants,
    }


def candidate_declarations():
    """既正式assetへ差分追記する候補値と単一SQL本文を返す。"""
    profile = candidate_profile()
    result = {
        name: []
        for name in (
            "tables",
            "functions",
            "policies",
            "acl_expectations",
            "column_acl_expectations",
        )
    }
    bodies = {}
    for row in profile["tables"]:
        result["tables"].append({k: v for k, v in row.items() if k != "owner"})
        name = row["table_id"]
        bodies[f"table|{name}"] = (
            f"ALTER TABLE sync_fence.{name} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE sync_fence.{name} FORCE ROW LEVEL SECURITY;\n"
            f"REVOKE ALL ON TABLE sync_fence.{name} FROM PUBLIC,pitchlog_app;\n"
        )
    for row in profile["functions"]:
        declaration = {k: v for k, v in row.items() if k != "sql"}
        result["functions"].append(declaration)
        identity = f"sync_right_api.{row['function_name']}({row['identity_args']})"
        sql = (
            re.sub(
                r"\ACREATE(?: OR REPLACE)? FUNCTION\s+(?=sync_right_api\.)",
                "CREATE FUNCTION ",
                row["sql"],
                count=1,
            )
            + f"\nALTER FUNCTION {identity} OWNER TO {_OWNER};\n"
            + f"REVOKE ALL ON FUNCTION {identity} FROM PUBLIC,pitchlog_app;\n"
        )
        if row["function_name"] != "consume_ordinary_projection":
            sql += f"GRANT EXECUTE ON FUNCTION {identity} TO pitchlog_app;\n"
        bodies["function|" + row["function_id"]] = sql
    for row in profile["policies"]:
        schema = row["schema_name"]
        declaration = {k: v for k, v in row.items() if k != "schema_name"}
        result["policies"].append(declaration)
        sql = (
            f"CREATE POLICY {row['policy_name']} ON "
            f"{schema}.{row['table_id']} FOR {row['command']} TO {_OWNER}"
        )
        if row["using_expression"] is not None:
            sql += f" USING ({row['using_expression']})"
        if row["with_check_expression"] is not None:
            sql += f" WITH CHECK ({row['with_check_expression']})"
        bodies["policy|" + row["policy_id"]] = sql + ";\n"
    grouped = {}
    for schema, table, privilege, columns in profile["grants"]:
        if columns is None:
            key = f"ACL:{schema}:{table}:{_OWNER}"
            result["acl_expectations"].append(
                {
                    "acl_id": key,
                    "object_kind": "table",
                    "object_schema": schema,
                    "object_id": table,
                    "profile": "function_only",
                    "grantee_role_id": _OWNER,
                    "privilege_ids": [privilege],
                    "grant_option": False,
                }
            )
            bodies["acl_expectation|" + key] = (
                f"GRANT {privilege} ON TABLE {schema}.{table} TO {_OWNER};\n"
            )
        else:
            for column in columns:
                key = f"COLUMN-ACL:{schema}:{table}:{column}:{_OWNER}"
                row = grouped.setdefault(
                    key,
                    {
                        "expectation_id": key,
                        "object_kind": "column",
                        "object_schema": schema,
                        "object_id": table,
                        "column_id": column,
                        "grantee_role_id": _OWNER,
                        "privilege_ids": [],
                        "grant_option": False,
                    },
                )
                row["privilege_ids"].append(privilege)
    result["column_acl_expectations"] = list(grouped.values())
    for key, row in grouped.items():
        clauses = ",".join(
            f"{privilege} ({row['column_id']})" for privilege in row["privilege_ids"]
        )
        bodies["column_acl_expectation|" + key] = (
            f"GRANT {clauses} ON TABLE {row['object_schema']}.{row['object_id']} "
            f"TO {_OWNER};\n"
        )
    return _plain_identifiers(copy.deepcopy(result)), _plain_identifiers(bodies)
