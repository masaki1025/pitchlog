"""実出場原本をowner-onlyの有限な認可宣言へ接続する。"""

from __future__ import annotations

import copy
import hashlib
from typing import Any

from sqlalchemy.dialects.postgresql import dialect

from pitchlog.db.game_state.pitcher_appearance_models import PitcherEntrySource
from pitchlog.domaingen.core import _canonical_hash
from pitchlog.repositories.stats_appearance import (
    candidate_appearance_context_function,
    candidate_appearance_source_function,
    candidate_private_entry_declarations,
)

INITIAL_OWNER = "pitchlog_initial_fn_owner"
WRITER_OWNER = "pitchlog_sync_right_fn_owner"
TABLE = "pitcher_entry_sources"
_COLUMN_PIN = "sha256:17ce78e60749a41cb34e18f8590215b181f17d5bc060f5dab55dbc5174919d03"
_PREDICATE = (
    "tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid"
)
_PARENT_PINS = {
    (
        "FUNCTION:stats_api:save_primitive_source(uuid, uuid, uuid, text, "
        "bigint, text, jsonb, bytea)"
    ): ("784b9244a2dafa96546b6328fadace7a79a72ba9981d7d1ad397ebc1054ddebf"),
    (
        "FUNCTION:sync_right_api:consume_nonplay_substitution(uuid, uuid, "
        "uuid, bytea, uuid, uuid, text)"
    ): ("616e9c917237be2f7cf7bb6e69cd724d87a3c9fed44ed72c88d90a2f467a1944"),
}
INITIAL_FUNCTION = (
    "FUNCTION:initial_right_api:insert_initial_grant(uuid, uuid, uuid, uuid, uuid, "
    "bigint, bigint, bytea, text, bytea, bytea)"
)
_INITIAL_PIN = "c5dc8a5f86c0cb437f15d7d35ac1b95ac0d98fdd9b0209e71ddb780c3efa5270"


def _columns() -> tuple[str, ...]:
    """未知の列追加を暗黙GRANTせず、既17列の全型から固定集合を検査する。"""
    table = PitcherEntrySource.__table__
    if any(c.server_default is not None for c in table.c):
        raise ValueError("投手出場原本へ未知defaultが追加されています")
    columns = {
        str(c.name): {
            "type": str(c.type.compile(dialect=dialect())),
            "nullable": c.nullable,
            "default": None,
        }
        for c in table.c
    }
    if (
        table.schema != "sync_fence"
        or table.name != TABLE
        or table.info.get("storage_owner") != "pitchlog_owner"
        or _canonical_hash(columns) != _COLUMN_PIN
    ):
        raise ValueError("投手出場原本の固定列集合が不一致")
    return tuple(columns)


def candidate_declarations() -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """既唯一projector/helperを使い、5関数と有限列だけを供給する。"""
    declarations, bodies = candidate_private_entry_declarations()
    declarations = copy.deepcopy(declarations)
    bodies = dict(bodies)
    expected_private = {
        (
            "initial_right_api",
            "persist_start_pitcher_entry",
            "uuid, uuid, bigint",
            INITIAL_OWNER,
        ),
        (
            "stats_api",
            "persist_writer_pitcher_entry",
            "uuid, uuid, uuid, bytea",
            WRITER_OWNER,
        ),
        ("stats_api", "protect_pitcher_entry_sources", "", WRITER_OWNER),
    }
    actual_private = {
        (r["schema_name"], r["function_name"], r["identity_args"], r["owner_role_id"])
        for r in declarations["functions"]
    }
    if (
        len(declarations["functions"]) != 3
        or actual_private != expected_private
        or any(
            r["acl_expectations"]
            or r["security_mode"] != "definer"
            or r["search_path"] != ["pg_catalog", "pg_temp"]
            for r in declarations["functions"]
        )
    ):
        raise ValueError("投手出場の既private helper集合が不一致")
    for name, args, returns, sql in (
        (
            "read_pitcher_appearance_context",
            "uuid, uuid",
            "TABLE(context_json text)",
            candidate_appearance_context_function(),
        ),
        (
            "read_pitcher_appearance_source",
            "uuid, uuid, boolean",
            "TABLE(record_json text)",
            candidate_appearance_source_function(),
        ),
    ):
        identity = f"FUNCTION:stats_api:{name}({args})"
        row = copy.deepcopy(
            next(
                r
                for r in declarations["functions"]
                if r["function_name"] == "persist_writer_pitcher_entry"
            )
        )
        row.update(
            function_id=identity,
            schema_name="stats_api",
            function_name=name,
            identity_args=args,
            returns=returns,
            volatility="stable",
        )
        declarations["functions"].append(row)
        bodies["function|" + identity] = sql
    declarations["tables"] = [
        {
            "table_id": TABLE,
            "schema_name": "sync_fence",
            "enable_row_level_security": True,
            "force_row_level_security": True,
        }
    ]
    bodies["table|" + TABLE] = (
        f"ALTER TABLE sync_fence.{TABLE} ENABLE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE sync_fence.{TABLE} FORCE ROW LEVEL SECURITY;\n"
        f"REVOKE ALL ON TABLE sync_fence.{TABLE} FROM PUBLIC,pitchlog_app,"
        "pitchlog_initial_actor,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor;\n"
    )
    for column in _columns():
        for owner in (INITIAL_OWNER, WRITER_OWNER):
            identity = f"COLUMN-ACL:sync_fence:{TABLE}:{column}:{owner}"
            declarations["column_acl_expectations"].append(
                {
                    "expectation_id": identity,
                    "object_kind": "column",
                    "object_schema": "sync_fence",
                    "object_id": TABLE,
                    "column_id": column,
                    "grantee_role_id": owner,
                    "privilege_ids": ["SELECT", "INSERT"],
                    "grant_option": False,
                }
            )
            bodies["column_acl_expectation|" + identity] = (
                f"GRANT SELECT ({column}),INSERT ({column}) "
                f"ON sync_fence.{TABLE} TO {owner};\n"
            )
    declarations["policies"] = []
    for command in ("SELECT", "INSERT"):
        name = "pitcher_entry_" + command.lower()
        identity = f"POLICY:{TABLE}:{name}"
        using = _PREDICATE if command == "SELECT" else None
        check = _PREDICATE if command == "INSERT" else None
        declarations["policies"].append(
            {
                "policy_id": identity,
                "table_id": TABLE,
                "profile": "function_only",
                "policy_name": name,
                "command": command,
                "policy_mode": "permissive",
                "role_ids": [INITIAL_OWNER, WRITER_OWNER],
                "using_predicate_id": None,
                "using_column": None,
                "using_expression": using,
                "with_check_predicate_id": None,
                "with_check_column": None,
                "with_check_expression": check,
            }
        )
        bodies["policy|" + identity] = (
            f"CREATE POLICY {name} ON sync_fence.{TABLE} AS PERMISSIVE "
            f"FOR {command} TO {INITIAL_OWNER},{WRITER_OWNER}"
            + (f" USING ({using})" if using else "")
            + (f" WITH CHECK ({check})" if check else "")
            + ";\n"
        )
    if tuple(
        len(declarations[s])
        for s in ("functions", "tables", "policies", "column_acl_expectations")
    ) != (5, 1, 2, 36):
        raise ValueError("投手出場の認可宣言集合が不一致")
    return declarations, bodies


def overlay_initial_function(function_id: str, sql: str) -> str:
    """既初期付与の成功点だけへ真正開始entryを同TXで追加する。"""
    if function_id != INITIAL_FUNCTION:
        return sql
    if hashlib.sha256(sql.encode()).hexdigest() != _INITIAL_PIN:
        raise ValueError("投手出場の初期付与元本文が不一致")
    marker = "    RETURN true;\nEXCEPTION"
    if sql.count(marker) != 1:
        raise ValueError("投手出場の初期付与成功点が一意でない")
    hook = """    IF EXISTS(
      SELECT 1 FROM public.games g WHERE g.tenant_id=p_tenant_id
      AND g.id=p_game_id AND g.status='in_progress' AND g.started_at IS NOT NULL
    ) THEN
      PERFORM initial_right_api.persist_start_pitcher_entry(
        p_tenant_id,p_attempt_id,p_generation);
    END IF;
"""
    return sql.replace(marker, hook + marker)


def overlay_saved_function(function_id: str, sql: str) -> str:
    """P3適用後の正規Save/交代原本へ結び、親末尾の再確認を維持する。"""
    if function_id not in _PARENT_PINS:
        return sql
    if hashlib.sha256(sql.encode()).hexdigest() != _PARENT_PINS[function_id]:
        raise ValueError("投手出場の保存元本文が不一致")
    if ":save_primitive_source(" in function_id:
        marker = (
            " PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,"
            "p_phase_id,p_binding_nonce,binding.device_id,binding.game_id);\n"
            " RETURN QUERY SELECT series.id"
        )
        # Save後audit直後の2点だけ。入口のbinding確認やP3を通過させない。
        prefix = (
            " IF event_row.event_kind='play_input' "
            "AND provider IN ('first_ball','ordinary') THEN\n"
            " PERFORM stats_api.persist_writer_pitcher_entry(\n"
            " p_attempt_id,p_phase_id,p_source_event_id,p_binding_nonce);\n END IF;\n"
        )
        if sql.count(marker) != 2:
            raise ValueError("投手出場Saveの末尾再確認が閉じた2点でない")
    else:
        marker = " RETURN QUERY SELECT true;"
        prefix = (
            " PERFORM stats_api.persist_writer_pitcher_entry(\n"
            " p_attempt_id,p_phase_id,own_event.id,p_binding_nonce);\n"
        )
        if sql.count(marker) != 1:
            raise ValueError("投手出場交代の保存成功点が一意でない")
    return sql.replace(marker, prefix + marker)
