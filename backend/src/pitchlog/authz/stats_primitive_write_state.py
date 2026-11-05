"""同TX native原本に閉じた成績writer前値の固定関数を供給する。"""

from __future__ import annotations

import re
from typing import Any

from pitchlog.authz import stats_primitive_product as product
from pitchlog.authz.stats_primitive_sql import candidate_function_bodies
from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

FUNCTION_NAME = "read_primitive_writer_state"
IDENTITY_ARGS = "uuid, uuid, uuid, text, bytea"
FUNCTION_ID = f"FUNCTION:stats_api:{FUNCTION_NAME}({IDENTITY_ARGS})"
_PARAMETERS = (
    ("p_attempt_id", "uuid"),
    ("p_phase_id", "uuid"),
    ("p_source_event_id", "uuid"),
    ("p_model_sha256", "text"),
    ("p_binding_nonce", "bytea"),
)
# 前値を取得する関数には未取得のCAS値を受けない。Save本体は一切変更しない。
_SAVE_CAS_ARGUMENT_CHECK = (
    "\n OR p_expected_revision IS NULL OR p_expected_revision<0"
    "\n OR ((p_expected_revision=0) IS DISTINCT "
    "FROM (p_expected_source_set_sha256 IS NULL))"
    "\n OR (p_expected_source_set_sha256 IS NOT NULL AND "
    "p_expected_source_set_sha256 !~ '^[a-f0-9]{64}$')"
)
_BEGIN = "\nBEGIN\n"
_HEALTH = "\n SELECT * INTO STRICT health FROM ("
_REQUIRED_GUARDS = (
    "session_user IS DISTINCT FROM 'pitchlog_app'",
    "current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'",
    "pg_catalog.octet_length(p_binding_nonce)<>32",
    "pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'off'",
    "b.state='open' AND b.transaction_id=own_xid",
    "b.expires_at>pg_catalog.clock_timestamp()",
    "PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,"
    "p_binding_nonce,binding.device_id,binding.game_id)",
    "s.state='consumed' AND s.consumed_at IS NOT NULL",
    "s.transaction_id=own_xid",
    "AND wa.transaction_id=own_xid AND wa.lease_id=b.lease_id",
    "pg_catalog.mod(own_xid::numeric,4294967296::numeric)",
    "SELECT p.* INTO STRICT saved_play FROM public.play_rows p",
    "SELECT * INTO STRICT current_source FROM (WITH canonical_scope",
    "current_source.source_fingerprint IS DISTINCT FROM binding.event_fingerprint",
)


def _source_guard() -> tuple[str, str]:
    """採用Saveの全binding/印/原本照合を再利用し、新しい計算を持たない。"""
    bodies = candidate_function_bodies()
    if set(bodies) != {
        "save_primitive_source",
        "open_primitive_snapshot",
        "read_play_export_primitives",
        "read_primitive_totals",
    }:
        raise ValueError("成績の採用済み4関数が不一致")
    source = bodies["save_primitive_source"]
    if source.count(_BEGIN) != 1 or source.count(_HEALTH) != 1:
        raise ValueError("成績writerの採用guard境界が不一致")
    prefix = source.split(_BEGIN, 1)[1].split(_HEALTH, 1)[0]
    if prefix.count(_SAVE_CAS_ARGUMENT_CHECK) != 1:
        raise ValueError("成績writerのCAS入力境界が不一致")
    prefix = prefix.replace(_SAVE_CAS_ARGUMENT_CHECK, "", 1)
    parameters = set(re.findall(r"\bp_[a-z0-9_]+\b", prefix))
    if parameters != {name for name, _ in _PARAMETERS} | {"p_game_id"}:
        raise ValueError("成績writerのguardに未知入力がある")
    if any(fragment not in prefix for fragment in _REQUIRED_GUARDS):
        raise ValueError("成績writerの実binding/consumed guardが欠落")
    if f"OR p_model_sha256 IS DISTINCT FROM '{SOURCE_MODEL_HASH}'" not in prefix:
        raise ValueError("成績writerの生成モデルが不一致")
    artifacts = re.findall(
        r"series\.t5_artifact_set_sha256 IS DISTINCT FROM '([a-f0-9]{64})'",
        source,
    )
    if len(artifacts) != 1:
        raise ValueError("成績writerの採用artifact集合が不一致")
    return prefix, artifacts[0]


def candidate_sql() -> str:
    """保存後の実writerだけに、同scopeのcurrent_open前値を1行返す。"""
    guard, artifact = _source_guard()
    signature = ",".join(name + " " + kind for name, kind in _PARAMETERS)
    return (
        f"CREATE FUNCTION stats_api.{FUNCTION_NAME}({signature})\n"
        "RETURNS TABLE(revision bigint,source_set_sha256 text) "
        "LANGUAGE plpgsql VOLATILE SECURITY DEFINER\n"
        "SET search_path=pg_catalog,pg_temp AS $stats_writer_state$\n"
        "#variable_conflict use_column\n"
        "DECLARE tenant uuid; own_xid text; p_game_id uuid;\n"
        " binding sync_fence.writer_bindings%ROWTYPE;\n"
        " event_row public.operation_events%ROWTYPE;\n"
        " saved_play public.play_rows%ROWTYPE;\n"
        " checkpoint sync_fence.ordinary_pitch_checkpoints%ROWTYPE;\n"
        " series sync_fence.stats_fact_versions%ROWTYPE;\n"
        " stamp jsonb; variant text; provider text;\n"
        " checkpoint_id uuid; checkpoint_revision bigint;\n"
        " checkpoint_digest text; frame_digest text; current_source record;\n"
        "BEGIN\n" + guard + "\n BEGIN\n"
        "  SELECT v.* INTO STRICT series FROM sync_fence.stats_fact_versions v\n"
        "  WHERE v.tenant_id=tenant AND v.game_id=p_game_id\n"
        "  AND v.model_sha256=p_model_sha256 AND v.is_current FOR UPDATE;\n"
        " EXCEPTION WHEN NO_DATA_FOUND THEN\n"
        "  IF EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions v\n"
        "   WHERE v.tenant_id=tenant AND v.game_id=p_game_id\n"
        "   AND v.model_sha256=p_model_sha256) THEN\n"
        "   RAISE EXCEPTION 'stats primitive boundary rejected' "
        "USING ERRCODE='42501';\n"
        "  END IF;\n"
        "  RETURN QUERY SELECT 0::bigint,NULL::text;\n"
        "  RETURN;\n"
        " END;\n"
        " IF series.is_current IS DISTINCT FROM true\n"
        " OR series.invalidated_at IS NOT NULL\n"
        " OR series.completion_state IS DISTINCT FROM 'current_open'\n"
        " OR series.revision IS NULL OR series.revision<1\n"
        " OR series.source_set_sha256 IS NULL\n"
        " OR series.source_set_sha256 !~ '^[a-f0-9]{64}$'\n"
        " OR series.rule_sha256 IS NULL OR series.rule_sha256 !~ '^[a-f0-9]{64}$'\n"
        " OR series.source_count IS NULL OR series.source_count<0\n"
        f" OR series.t5_artifact_set_sha256 IS DISTINCT FROM '{artifact}' THEN\n"
        "  RAISE EXCEPTION 'stats primitive boundary rejected' "
        "USING ERRCODE='42501';\n"
        " END IF;\n"
        " RETURN QUERY SELECT series.revision,series.source_set_sha256;\n"
        "END;\n$stats_writer_state$;\n"
    )


def candidate_declarations() -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """既70列/10policyへ触れず、既ownerの新関数1だけを別供給する。"""
    declaration = {
        "function_id": FUNCTION_ID,
        "schema_name": "stats_api",
        "function_name": FUNCTION_NAME,
        "identity_args": IDENTITY_ARGS,
        "function_kind": "definer",
        "owner_role_id": product.OWNER,
        "language": "plpgsql",
        "returns": "TABLE(revision bigint,source_set_sha256 text)",
        "security_mode": "definer",
        "volatility": "volatile",
        "search_path": ["pg_catalog", "pg_temp"],
        "acl_expectations": [
            {"grantee": product.APP, "privilege": "EXECUTE", "grantable": False}
        ],
        "revoked_acl_expectations": [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
        ],
    }
    return {"functions": [declaration]}, {"function|" + FUNCTION_ID: candidate_sql()}


def function_application_body(function_id: str) -> str | None:
    """同じ既owner/ACL footerだけを追加し、適用や新grantは行わない。"""
    if function_id != FUNCTION_ID:
        return None
    declarations, bodies = candidate_declarations()
    return product._application_body(
        declarations["functions"][0], bodies["function|" + FUNCTION_ID]
    )


def operation_candidate() -> dict[str, Any]:
    """rootのsame-frame private gateを別必須とする前値operationを宣言する。"""
    return {
        "operation_id": "STATS_PRIMITIVES:read_writer_state",
        "capability_id": "CAP:stats_primitives:save_source",
        "function_id": FUNCTION_ID,
        "parameters": [{"name": name, "sql_type": kind} for name, kind in _PARAMETERS],
        "results": [
            {"name": "revision", "sql_type": "bigint", "nullable": False},
            {"name": "source_set_sha256", "sql_type": "text", "nullable": True},
        ],
        "min_rows": 1,
        "max_rows": 1,
        "qualification": (
            "root same consumed native frame/handle/TX/nonce; not value authority"
        ),
    }


def validate_candidate_sql(value: object) -> None:
    """正式採否前の本文がcanonical全値と異なる場合は必ず拒否する。"""
    if type(value) is not str or value != candidate_sql():
        raise ValueError("成績writer前値SQLのcanonical全値が不一致")
