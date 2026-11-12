"""取消の私有6関数と必要列権限を描画する。適用・受理は行わない。"""

from __future__ import annotations

import re

from sqlalchemy.dialects import postgresql

from pitchlog.authz.nonplay_prefix_sql import candidate_function_bodies
from pitchlog.authz.stats_primitive_product import _add_column, _add_policy
from pitchlog.db.writer_binding.nonplay_models import NonplayWriteAdmission
from pitchlog.domaingen.core import _canonical_hash

_OWNER = "pitchlog_sync_right_fn_owner"
_TABLE = "nonplay_write_admissions"
_COLUMNS_HASH = (
    "sha256:22a10fddb519d6738f9eef09f076cc52a24bc61b45d410f97d249c7f3db3045f"
)
_MUTABLE = frozenset(
    {
        "artifact_sha256",
        "checkpoint_digest",
        "checkpoint_id",
        "checkpoint_revision",
        "consumed_at",
        "frame_digest",
        "frame_id",
        "preparation",
        "preparation_json",
        "source_d1",
        "source_event_id",
        "state",
        "target_d1",
        "target_event_id",
        "target_generation",
        "target_play_id",
    }
)
_COMMON = "uuid, uuid, uuid, bytea, uuid, uuid"
_FUNCTIONS = {
    "bind_nonplay_device": (_COMMON + ", bytea", "device_matches boolean"),
    "check_nonplay_right": (
        _COMMON + ", bigint, bigint, bytea",
        "recovery_matches boolean, right_matches boolean",
    ),
    "lock_nonplay_checkpoint": (_COMMON + ", text", "record_json text"),
    "read_nonplay_history_page": (_COMMON + ", text", "record_json text"),
    "prepare_nonplay_undo": (_COMMON + ", text", "prepared boolean"),
    "consume_nonplay_undo": (_COMMON + ", text", "receipt_json text"),
    "consume_nonplay_substitution": (_COMMON + ", text", "consumed boolean"),
    "consume_nonplay_tiebreak_start": (_COMMON + ", text", "consumed boolean"),
}
_PREDICATE = (
    "tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid"
    " AND session_user = 'pitchlog_app'"
)


def candidate_declarations():
    """固定model・唯一SQLからdescriptorと本文を返す。DBへは接続しない。"""
    table = NonplayWriteAdmission.__table__
    columns = {
        str(c.name): {
            "type": str(c.type.compile(dialect=postgresql.dialect())),
            "nullable": c.nullable,
        }
        for c in table.c
    }
    if (
        table.schema != "sync_fence"
        or table.name != _TABLE
        or len(columns) != 43
        or _canonical_hash(columns) != _COLUMNS_HASH
        or NonplayWriteAdmission.immutability.conditional_update_columns != _MUTABLE
    ):
        raise ValueError("取消の採用済み43列・可変列と不一致です")
    declarations = {
        name: []
        for name in (
            "tables",
            "functions",
            "policies",
            "acl_expectations",
            "column_acl_expectations",
        )
    }
    declarations["tables"].append(
        {
            "table_id": _TABLE,
            "schema_name": "sync_fence",
            "enable_row_level_security": True,
            "force_row_level_security": True,
        }
    )
    bodies = {
        "table|" + _TABLE: (
            f"ALTER TABLE sync_fence.{_TABLE} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE sync_fence.{_TABLE} FORCE ROW LEVEL SECURITY;\n"
            f"REVOKE ALL ON TABLE sync_fence.{_TABLE} FROM PUBLIC,pitchlog_app;\n"
        )
    }
    from pitchlog.authz.substitution_sql import candidate_substitution_function_body
    from pitchlog.authz.tiebreak_sql import candidate_tiebreak_start_function_body

    sql_bodies = candidate_function_bodies() | {
        "consume_nonplay_substitution": candidate_substitution_function_body(),
        "consume_nonplay_tiebreak_start": candidate_tiebreak_start_function_body(),
    }
    if set(sql_bodies) != set(_FUNCTIONS):
        raise ValueError("非playの固定関数集合が不一致です")
    for name, (identity, returns) in _FUNCTIONS.items():
        sql = sql_bodies[name]
        match = re.match(
            r"CREATE(?: OR REPLACE)? FUNCTION sync_right_api\.(\w+)\((.*?)\)"
            r"\s*RETURNS TABLE\s*\((.*?)\) LANGUAGE plpgsql VOLATILE "
            r"SECURITY DEFINER\s*SET search_path\s*=\s*pg_catalog,pg_temp AS ",
            sql,
            re.S,
        )
        if (
            match is None
            or match[1] != name
            or ", ".join(arg.strip().split()[-1] for arg in match[2].split(","))
            != identity
            or ", ".join(arg.strip() for arg in match[3].split(",")) != returns
        ):
            raise ValueError("取消の固定SQL署名・実行属性が不一致です")
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
                "returns": "TABLE(" + returns + ")",
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
                    {
                        "grantee": "PUBLIC",
                        "privilege": "EXECUTE",
                        "grantable": False,
                    }
                ],
            }
        )
        full_name = f"sync_right_api.{name}({identity})"
        bodies["function|" + key] = (
            re.sub(r"\ACREATE OR REPLACE FUNCTION", "CREATE FUNCTION", sql)
            + f"\nALTER FUNCTION {full_name} OWNER TO {_OWNER};\n"
            + f"REVOKE ALL ON FUNCTION {full_name} FROM PUBLIC,pitchlog_app;\n"
            + f"GRANT EXECUTE ON FUNCTION {full_name} TO pitchlog_app;\n"
        )
    # system xmin照合は列GRANTで代用せず、既admissionと同じ表SELECTに閉じる。
    acl = f"ACL:sync_fence:{_TABLE}:{_OWNER}"
    declarations["acl_expectations"].append(
        {
            "acl_id": acl,
            "object_kind": "table",
            "object_schema": "sync_fence",
            "object_id": _TABLE,
            "profile": "function_only",
            "grantee_role_id": _OWNER,
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        }
    )
    bodies["acl_expectation|" + acl] = (
        f"GRANT SELECT ON TABLE sync_fence.{_TABLE} TO {_OWNER};\n"
    )
    for column in columns:
        # bind時のidentity/state INSERTと、prepare/consumeの有限UPDATEだけ。
        privileges = ["INSERT"] if column not in _MUTABLE or column == "state" else []
        if column in _MUTABLE:
            privileges.append("UPDATE")
        _add_nonplay_column(declarations, bodies, column, privileges)
    for command in ("SELECT", "INSERT", "UPDATE"):
        _add_policy(
            declarations,
            bodies,
            "sync_fence",
            _TABLE,
            "nonplay_" + command.lower(),
            command,
            _PREDICATE,
        )
    receipt_table = "substitution_write_receipts"
    declarations["tables"].append(
        {
            "table_id": receipt_table,
            "schema_name": "sync_fence",
            "enable_row_level_security": True,
            "force_row_level_security": True,
        }
    )
    bodies["table|" + receipt_table] = (
        f"ALTER TABLE sync_fence.{receipt_table} ENABLE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE sync_fence.{receipt_table} FORCE ROW LEVEL SECURITY;\n"
        f"REVOKE ALL ON TABLE sync_fence.{receipt_table} FROM PUBLIC,pitchlog_app;\n"
    )
    receipt_acl = f"ACL:sync_fence:{receipt_table}:{_OWNER}"
    declarations["acl_expectations"].append(
        {
            "acl_id": receipt_acl,
            "object_kind": "table",
            "object_schema": "sync_fence",
            "object_id": receipt_table,
            "profile": "function_only",
            "grantee_role_id": _OWNER,
            "privilege_ids": ["SELECT", "INSERT"],
            "grant_option": False,
        }
    )
    bodies["acl_expectation|" + receipt_acl] = (
        f"GRANT SELECT,INSERT ON TABLE sync_fence.{receipt_table} TO {_OWNER};\n"
    )
    for command in ("SELECT", "INSERT"):
        _add_policy(
            declarations,
            bodies,
            "sync_fence",
            receipt_table,
            "substitution_receipt_" + command.lower(),
            command,
            _PREDICATE,
        )
    tiebreak_receipt_table = "tiebreak_start_write_receipts"
    declarations["tables"].append(
        {
            "table_id": tiebreak_receipt_table,
            "schema_name": "sync_fence",
            "enable_row_level_security": True,
            "force_row_level_security": True,
        }
    )
    bodies["table|" + tiebreak_receipt_table] = (
        f"ALTER TABLE sync_fence.{tiebreak_receipt_table} ENABLE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE sync_fence.{tiebreak_receipt_table} FORCE ROW LEVEL SECURITY;\n"
        f"REVOKE ALL ON TABLE sync_fence.{tiebreak_receipt_table} FROM PUBLIC,pitchlog_app;\n"
    )
    tiebreak_receipt_acl = f"ACL:sync_fence:{tiebreak_receipt_table}:{_OWNER}"
    declarations["acl_expectations"].append(
        {
            "acl_id": tiebreak_receipt_acl,
            "object_kind": "table",
            "object_schema": "sync_fence",
            "object_id": tiebreak_receipt_table,
            "profile": "function_only",
            "grantee_role_id": _OWNER,
            "privilege_ids": ["SELECT", "INSERT"],
            "grant_option": False,
        }
    )
    bodies["acl_expectation|" + tiebreak_receipt_acl] = (
        f"GRANT SELECT,INSERT ON TABLE sync_fence.{tiebreak_receipt_table} TO {_OWNER};\n"
    )
    for command in ("SELECT", "INSERT"):
        _add_policy(
            declarations,
            bodies,
            "sync_fence",
            tiebreak_receipt_table,
            "tiebreak_start_receipt_" + command.lower(),
            command,
            _PREDICATE,
        )
    key = f"COLUMN-ACL:public:play_rows:hidden_at:{_OWNER}"
    declarations["column_acl_expectations"].append(
        {
            "expectation_id": key,
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "play_rows",
            "column_id": "hidden_at",
            "grantee_role_id": _OWNER,
            "privilege_ids": ["UPDATE"],
            "grant_option": False,
        }
    )
    bodies["column_acl_expectation|" + key] = (
        f"GRANT UPDATE (hidden_at) ON TABLE public.play_rows TO {_OWNER};\n"
    )
    _add_policy(
        declarations,
        bodies,
        "public",
        "play_rows",
        "nonplay_hide",
        "UPDATE",
        _PREDICATE,
    )
    # 実owned roleで不足を確認した列だけ。全表SELECTへ拡張しない。
    for table_name, column in (
        ("idempotency_ledger", "result"),
        ("idempotency_ledger", "reason"),
        ("event_slots", "xmin"),
    ):
        _add_column(declarations, bodies, "public", table_name, column, ["SELECT"])
    return declarations, bodies


def _add_nonplay_column(declarations, bodies, column, privileges):
    """新表だけのINSERT/UPDATEを描画し、共通helperの許可集合を変えない。"""
    if privileges not in (["INSERT"], ["UPDATE"], ["INSERT", "UPDATE"]):
        raise ValueError("取消の列DML集合が不一致です")
    key = f"COLUMN-ACL:sync_fence:{_TABLE}:{column}:{_OWNER}"
    declarations["column_acl_expectations"].append(
        {
            "expectation_id": key,
            "object_kind": "column",
            "object_schema": "sync_fence",
            "object_id": _TABLE,
            "column_id": column,
            "grantee_role_id": _OWNER,
            "privilege_ids": privileges,
            "grant_option": False,
        }
    )
    clauses = ",".join(f"{p} ({column})" for p in privileges)
    bodies["column_acl_expectation|" + key] = (
        f"GRANT {clauses} ON TABLE sync_fence.{_TABLE} TO {_OWNER};\n"
    )
