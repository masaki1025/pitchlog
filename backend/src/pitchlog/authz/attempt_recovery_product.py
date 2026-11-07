"""旧試行遮断の固定 SQL から製品認可の閉じた候補差分を導出する。"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

_OWNER = "pitchlog_sync_binding_fn_owner"
_ACTOR = "pitchlog_sync_binding_actor"
_SOURCE = (
    Path(__file__).parents[1] / "sync/control_provider/sql/writer-binding-functions.sql"
)
_OLD_BODY_SHA = {
    "publish_writer_binding": (
        "85d9db013c33f71a9267e7da1a4db7989aab1e14d22f81e7adc57ddafcb82d0d"
    ),
    "guard_writer_records": (
        "c503ae220c04a0b12ecf0015a1e77592de36a07f57cede60c5a50f0f0f1ef7b4"
    ),
}


def _function_sql(source: str, name: str) -> str:
    """唯一の CREATE 本文を固定 bundle から取り出す。"""
    matches = re.findall(
        rf"CREATE FUNCTION sync_fence_api\.{re.escape(name)}\([^\n]*\)\n"
        r".*?END;\$f\$;",
        source,
        flags=re.DOTALL,
    )
    if len(matches) != 1:
        raise ValueError("旧試行遮断の関数本文が一意でない")
    return matches[0] + "\n"


def upgrade_function_sql(name: str) -> str:
    """旧版全値確認後の限定migrationが置換する固定2関数だけを返す。"""
    if name not in _OLD_BODY_SHA:
        raise ValueError("退役関数の移行対象が不正")
    source = _SOURCE.read_text(encoding="utf-8")
    return _function_sql(source, name).replace(
        "CREATE FUNCTION ", "CREATE OR REPLACE FUNCTION ", 1
    )


def upgrade_trigger_sql() -> tuple[str, str]:
    """既4triggerを保持し、退役表の不変guard二件だけを増やす。"""
    source = _SOURCE.read_text(encoding="utf-8")
    values = re.findall(r"CREATE TRIGGER sync_attempt_retirement_[^;]+;", source)
    if len(values) != 2:
        raise ValueError("退役guard triggerが二件でない")
    return values[0], values[1]


def _header(kind: str, identifier: str) -> str:
    return f"-- ELEMENT-TYPE: {kind}\n-- ELEMENT-ID: {identifier}\n\n"


def _function_row(
    name: str, args: str, result: str, *, trigger: bool = False
) -> dict[str, Any]:
    identifier = f"FUNCTION:sync_fence_api:{name}({args})"
    return {
        "function_id": identifier,
        "schema_name": "sync_fence_api",
        "function_name": name,
        "identity_args": args,
        "function_kind": "definer",
        "owner_role_id": _OWNER,
        "language": "plpgsql",
        "returns": result,
        "security_mode": "definer",
        "volatility": "volatile",
        "search_path": ["pg_catalog", "pg_temp"],
        "acl_expectations": []
        if trigger
        else [{"grantee": _ACTOR, "privilege": "EXECUTE", "grantable": False}],
        "revoked_acl_expectations": [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
            {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False},
        ],
    }


def connection_declarations(
    existing_bodies: dict[str, str],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """既関数は凍結旧byteを確認し、必要な2関数と最小 ACL を追加する。"""
    for name, expected_sha in _OLD_BODY_SHA.items():
        key = next(
            (
                key
                for key in existing_bodies
                if key.startswith("function|") and f":{name}(" in key
            ),
            None,
        )
        if (
            key is None
            or hashlib.sha256(existing_bodies[key].encode()).hexdigest() != expected_sha
        ):
            raise ValueError("旧試行遮断の既関数原本が不一致")
    source = _SOURCE.read_text(encoding="utf-8")
    declarations: dict[str, list[dict[str, Any]]] = {
        "tables": [
            {
                "table_id": "attempt_retirements",
                "schema_name": "sync_fence",
                "enable_row_level_security": True,
                "force_row_level_security": True,
            }
        ],
        "policies": [
            {
                "policy_id": "POLICY:attempt_retirements:attempt_retirement_owner",
                "table_id": "attempt_retirements",
                "profile": "function_only",
                "policy_name": "attempt_retirement_owner",
                "command": "ALL",
                "policy_mode": "permissive",
                "role_ids": [_OWNER],
                "using_predicate_id": None,
                "using_column": None,
                "using_expression": "true",
                "with_check_predicate_id": None,
                "with_check_column": None,
                "with_check_expression": "true",
            },
            {
                "policy_id": "POLICY:idempotency_ledger:binding_d5_read",
                "table_id": "idempotency_ledger",
                "profile": "function_only",
                "policy_name": "binding_d5_read",
                "command": "SELECT",
                "policy_mode": "permissive",
                "role_ids": [_OWNER],
                "using_predicate_id": None,
                "using_column": None,
                "using_expression": "true",
                "with_check_predicate_id": None,
                "with_check_column": None,
                "with_check_expression": None,
            },
        ],
        "functions": [
            _function_row("read_attempt_d5", "uuid, uuid, text", "text"),
            _function_row(
                "retire_sync_attempt",
                "uuid, uuid, uuid, uuid, uuid, text, bigint, text, text, uuid, bigint",
                "text",
            ),
        ],
        "acl_expectations": [
            {
                "acl_id": f"ACL:sync_fence:attempt_retirements:{_OWNER}",
                "object_kind": "table",
                "object_schema": "sync_fence",
                "object_id": "attempt_retirements",
                "profile": "function_only",
                "grantee_role_id": _OWNER,
                "privilege_ids": ["SELECT", "INSERT"],
                "grant_option": False,
            }
        ],
        "column_acl_expectations": [
            {
                "expectation_id": (
                    f"COLUMN-ACL:public:idempotency_ledger:{column}:{_OWNER}"
                ),
                "object_kind": "column",
                "object_schema": "public",
                "object_id": "idempotency_ledger",
                "column_id": column,
                "grantee_role_id": _OWNER,
                "privilege_ids": ["SELECT"],
                "grant_option": False,
            }
            for column in ("tenant_id", "d5", "source_fingerprint")
        ],
    }
    bodies: dict[str, str] = {}
    for row in declarations["functions"]:
        name = row["function_name"]
        identifier = row["function_id"]
        identity = f"sync_fence_api.{name}({row['identity_args']})"
        bodies["function|" + identifier] = (
            _header("function", identifier)
            + _function_sql(source, name)
            + f"ALTER FUNCTION {identity} OWNER TO {_OWNER};\n"
            + f"REVOKE ALL ON FUNCTION {identity} FROM PUBLIC,pitchlog_app;\n"
            + f"GRANT EXECUTE ON FUNCTION {identity} TO {_ACTOR};\n"
        )
    for name in _OLD_BODY_SHA:
        identifier = next(
            key.split("|", 1)[1]
            for key in existing_bodies
            if key.startswith("function|") and f":{name}(" in key
        )
        identity = identifier.split(":", 2)[2]
        suffix = (
            f"ALTER FUNCTION sync_fence_api.{identity} OWNER TO {_OWNER};\n"
            f"REVOKE ALL ON FUNCTION sync_fence_api.{identity} FROM PUBLIC;\n"
        )
        if name == "publish_writer_binding":
            suffix += (
                f"GRANT EXECUTE ON FUNCTION sync_fence_api.{identity} TO {_ACTOR};\n"
            )
        else:
            trigger_sql = re.findall(
                r"CREATE TRIGGER sync_(?:writer_binding|writer_admission|"
                r"attempt_retirement)_[^;]+;",
                source,
            )
            if len(trigger_sql) != 6:
                raise ValueError("writer guard triggerが六件でない")
            suffix += "\n".join(trigger_sql) + "\n"
        bodies["function|" + identifier] = (
            _header("function", identifier) + _function_sql(source, name) + suffix
        )
    table = "attempt_retirements"
    bodies["table|" + table] = _header("table", table) + (
        "ALTER TABLE sync_fence.attempt_retirements ENABLE ROW LEVEL SECURITY;\n"
        "ALTER TABLE sync_fence.attempt_retirements FORCE ROW LEVEL SECURITY;\n"
        "REVOKE ALL ON TABLE sync_fence.attempt_retirements FROM "
        "PUBLIC,pitchlog_app,pitchlog_sync_binding_actor;\n"
    )
    for row in declarations["policies"]:
        identifier = row["policy_id"]
        table_schema = "sync_fence" if row["table_id"] == table else "public"
        suffix = " WITH CHECK (true)" if row["command"] == "ALL" else ""
        bodies["policy|" + identifier] = _header("policy", identifier) + (
            f"CREATE POLICY {row['policy_name']} ON {table_schema}.{row['table_id']} "
            f"FOR {row['command']} TO {_OWNER} USING (true){suffix};\n"
        )
    for row in declarations["acl_expectations"]:
        identifier = row["acl_id"]
        bodies["acl_expectation|" + identifier] = _header(
            "acl_expectation", identifier
        ) + (f"GRANT SELECT,INSERT ON TABLE sync_fence.{table} TO {_OWNER};\n")
    for row in declarations["column_acl_expectations"]:
        identifier = row["expectation_id"]
        bodies["column_acl_expectation|" + identifier] = _header(
            "column_acl_expectation", identifier
        ) + (
            f"GRANT SELECT ({row['column_id']}) ON TABLE "
            f"public.idempotency_ledger TO {_OWNER};\n"
        )
    return declarations, bodies
