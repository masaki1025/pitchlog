"""終了再開の限定関数・認可を既製品publisherへ描画する。"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.dialects import postgresql

from pitchlog.authz.game_lifecycle_sql import candidate_function_bodies
from pitchlog.authz.stats_primitive_product import _add_policy
from pitchlog.db.writer_binding.lifecycle_models import (
    GameLifecycleHead,
    LifecycleWriteAdmission,
)
from pitchlog.domaingen.core import _canonical_hash

_OWNER = "pitchlog_sync_right_fn_owner"
_TENANT = (
    "tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid"
    " AND session_user = 'pitchlog_app'"
)
_FUNCTIONS = {
    "read_lifecycle_state": (
        "uuid, uuid, uuid, bytea, uuid, uuid, text",
        "record_json text",
    ),
    "prepare_game_lifecycle": (
        "uuid, uuid, uuid, bytea, uuid, uuid, text",
        "prepared boolean",
    ),
    "consume_game_lifecycle": (
        "uuid, uuid, uuid, bytea, uuid, uuid, text",
        "record_json text",
    ),
    "read_lifecycle_display": ("uuid, uuid", "record_json text"),
}
_TABLES = {
    "lifecycle_write_admissions": (
        LifecycleWriteAdmission,
        42,
        "sha256:ae9614171a8ef433d8bcbe5f4ac74367513f4d0a88b4e29a8af61b704ded1aa7",
        frozenset({"state", "consumed_at"}),
    ),
    "game_lifecycle_heads": (
        GameLifecycleHead,
        9,
        "sha256:d07af8c6c45ae5d3accf555e3af84214d9d48855f463564e4bf0e89314b0ef0f",
        frozenset(
            {
                "last_version",
                "is_finished",
                "active_end_event_id",
                "active_receipt_id",
                "active_stats_version_id",
                "last_control_event_id",
                "updated_at",
            }
        ),
    ),
}


def _column(declarations, bodies, schema, table, column, privileges):
    """有限列のgrant optionなしACLを描画する。"""
    if not privileges or set(privileges) - {"SELECT", "INSERT", "UPDATE"}:
        raise ValueError("終了再開の未知列権限です")
    key = f"COLUMN-ACL:{schema}:{table}:{column}:{_OWNER}"
    declarations["column_acl_expectations"].append(
        {
            "expectation_id": key,
            "object_kind": "column",
            "object_schema": schema,
            "object_id": table,
            "column_id": column,
            "grantee_role_id": _OWNER,
            "privilege_ids": privileges,
            "grant_option": False,
        }
    )
    clause = ",".join(f"{p} ({column})" for p in privileges)
    bodies["column_acl_expectation|" + key] = (
        f"GRANT {clause} ON TABLE {schema}.{table} TO {_OWNER};\n"
    )


def _consumed(table, *, action=None, receipt=None):
    """同TXで消費された同game印を旧表の書込へ束縛する。"""
    conditions = [
        f"a.tenant_id={table}.tenant_id",
        f"a.game_id={table}.{'id' if table == 'games' else 'game_id'}",
        "a.state='consumed'",
        "a.transaction_id=pg_catalog.pg_current_xact_id()::text",
    ]
    if action is not None:
        conditions.append(f"a.action='{action}'")
    if receipt is not None:
        conditions.append(f"a.receipt_id={receipt}")
    return (
        "EXISTS(SELECT 1 FROM sync_fence.lifecycle_write_admissions a WHERE "
        + " AND ".join(conditions)
        + ")"
    )


def candidate_declarations() -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """固定modelと唯一SQLから正式descriptor/本文だけを生成する。"""
    sections = (
        "tables",
        "functions",
        "policies",
        "acl_expectations",
        "column_acl_expectations",
    )
    declarations: dict[str, list[dict[str, Any]]] = {k: [] for k in sections}
    bodies: dict[str, str] = {}
    for name, (model, count, digest, mutable) in _TABLES.items():
        table = model.__table__
        columns = {
            str(c.name): {
                "type": str(c.type.compile(dialect=postgresql.dialect())),
                "nullable": c.nullable,
            }
            for c in table.c
        }
        if (
            table.schema != "sync_fence"
            or table.name != name
            or len(columns) != count
            or _canonical_hash(columns) != digest
            or model.immutability.conditional_update_columns != mutable
        ):
            raise ValueError("終了再開表の固定列/可変列が不一致です")
        declarations["tables"].append(
            {
                "table_id": name,
                "schema_name": "sync_fence",
                "enable_row_level_security": True,
                "force_row_level_security": True,
            }
        )
        bodies["table|" + name] = (
            f"ALTER TABLE sync_fence.{name} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE sync_fence.{name} FORCE ROW LEVEL SECURITY;\n"
            f"REVOKE ALL ON TABLE sync_fence.{name} FROM PUBLIC,pitchlog_app;\n"
        )
        for column in columns:
            rights = ["SELECT", "INSERT"] + (["UPDATE"] if column in mutable else [])
            _column(declarations, bodies, "sync_fence", name, column, rights)
        for command in ("SELECT", "INSERT", "UPDATE"):
            predicate = _TENANT
            if command != "SELECT":
                predicate += (
                    " AND " + _consumed(name)
                    if name == "game_lifecycle_heads"
                    else " AND transaction_id=pg_catalog.pg_current_xact_id()::text"
                )
            _add_policy(
                declarations,
                bodies,
                "sync_fence",
                name,
                "lifecycle_" + command.lower(),
                command,
                predicate,
            )
    # control bridgeはadmissionのsystem xminを読む。列GRANTでは代用しない。
    acl = f"ACL:sync_fence:lifecycle_write_admissions:{_OWNER}"
    declarations["acl_expectations"].append(
        {
            "acl_id": acl,
            "object_kind": "table",
            "object_schema": "sync_fence",
            "object_id": "lifecycle_write_admissions",
            "profile": "function_only",
            "grantee_role_id": _OWNER,
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        }
    )
    bodies["acl_expectation|" + acl] = (
        f"GRANT SELECT ON TABLE sync_fence.lifecycle_write_admissions TO {_OWNER};\n"
    )
    sql_bodies = candidate_function_bodies()
    if set(sql_bodies) != set(_FUNCTIONS):
        raise ValueError("終了再開の関数集合が不一致です")
    for name, (identity, result) in _FUNCTIONS.items():
        sql = sql_bodies[name]
        match = re.match(
            r"CREATE FUNCTION sync_right_api\.(\w+)\((.*?)\)\s*"
            r"RETURNS TABLE\((.*?)\) LANGUAGE plpgsql VOLATILE SECURITY DEFINER\s*"
            r"SET search_path=pg_catalog,pg_temp AS ",
            sql,
            re.S,
        )
        if (
            match is None
            or match[1] != name
            or ", ".join(a.strip().split()[-1] for a in match[2].split(",")) != identity
            or ", ".join(a.strip() for a in match[3].split(",")) != result
        ):
            raise ValueError("終了再開の関数署名/属性が不一致です")
        key = f"FUNCTION:sync_right_api:{name}({identity})"
        declarations["functions"].append(
            {
                "function_id": key,
                "schema_name": "sync_right_api",
                "function_name": name,
                "identity_args": identity,
                "function_kind": "definer",
                "owner_role_id": _OWNER,
                "language": "plpgsql",
                "returns": "TABLE(" + result + ")",
                "security_mode": "definer",
                "volatility": "volatile",
                "search_path": ["pg_catalog", "pg_temp"],
                "acl_expectations": [
                    {
                        "grantee": "pitchlog_app",
                        "privilege": "EXECUTE",
                        "grantable": False,
                    }
                ],
                "revoked_acl_expectations": [
                    {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
                ],
            }
        )
        full = f"sync_right_api.{name}({identity})"
        bodies["function|" + key] = (
            sql + f"\nALTER FUNCTION {full} OWNER TO {_OWNER};\n"
            f"REVOKE ALL ON FUNCTION {full} FROM PUBLIC,pitchlog_app;\n"
            f"GRANT EXECUTE ON FUNCTION {full} TO pitchlog_app;\n"
        )
    # 既SELECTのゲームstatusだけUPDATEへ広げる。appには直接grantしない。
    _column(declarations, bodies, "public", "games", "status", ["SELECT", "UPDATE"])
    for column in ("started_at", "import_batch_id"):
        _column(declarations, bodies, "public", "games", column, ["SELECT"])
    _add_policy(
        declarations,
        bodies,
        "public",
        "games",
        "lifecycle_status_update",
        "UPDATE",
        _TENANT + " AND " + _consumed("games"),
    )
    # stats既current_open限定を維持し、真正同TX印の終了版だけを追加する。
    _add_policy(
        declarations,
        bodies,
        "sync_fence",
        "stats_fact_versions",
        "lifecycle_end_insert",
        "INSERT",
        _TENANT
        + " AND completion_state='confirmed_ended' AND "
        + _consumed(
            "stats_fact_versions",
            action="end",
            receipt="stats_fact_versions.completion_receipt_id",
        ),
    )
    _add_policy(
        declarations,
        bodies,
        "sync_fence",
        "stats_fact_versions",
        "lifecycle_reopen_update",
        "UPDATE",
        _TENANT
        + " AND completion_state='confirmed_ended' AND "
        + _consumed("stats_fact_versions", action="reopen"),
    )
    for table in ("stats_primitive_sources", "stats_primitive_facts"):
        parent = (
            "EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions v WHERE "
            f"v.tenant_id={table}.tenant_id AND v.game_id={table}.game_id "
            f"AND v.id={table}.fact_version_id AND v.is_current "
            "AND v.invalidated_at IS NULL "
            "AND v.completion_state='confirmed_ended' AND "
            + _consumed("v", action="end", receipt="v.completion_receipt_id")
            + ")"
        )
        _add_policy(
            declarations,
            bodies,
            "sync_fence",
            table,
            "lifecycle_end_insert",
            "INSERT",
            _TENANT + " AND " + parent,
        )
    return declarations, bodies
