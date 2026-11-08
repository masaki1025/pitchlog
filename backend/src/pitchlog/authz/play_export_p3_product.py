"""P3 CSV専用の保存構造/同writer原本query候補。正式登録はrootが行う。"""

from __future__ import annotations

import json
from pathlib import Path

from pitchlog.authz.play_export_source_read_product import candidate_read_bundle
from pitchlog.authz.play_export_writer_product import _bound_generated_query
from pitchlog.domaingen.play_export_score import generate_play_export_score_bundle

_ROOT = Path(__file__).resolve().parents[4]
_OWNER = "pitchlog_sync_right_fn_owner"
_TABLE = "sync_fence.play_export_p3_snapshots"
_COLUMNS = (
    ("tenant_id", "uuid"),
    ("game_id", "uuid"),
    ("internal_generation", "bigint"),
    ("capsule_id", "uuid"),
    ("d1", "bigint"),
    ("original_play_row_id", "uuid"),
    ("effective_event_id", "uuid"),
    ("effective_play_row_id", "uuid"),
    ("play_row_version", "bigint"),
    ("item_digest", "text"),
    ("capsule_source_set_digest", "text"),
    ("capsule_stats_version_id", "uuid"),
    ("plays_csv_json", "jsonb"),
    ("full_innings_json", "jsonb"),
    ("runner_rows_json", "jsonb"),
    ("reference_json", "jsonb"),
    ("captured_at", "timestamp with time zone"),
)


def storage_declaration() -> dict:
    """新表だけの明示構造を返し、番号/旧migration/正式catalogを変更しない。"""
    return {
        "schema": "sync_fence",
        "name": "play_export_p3_snapshots",
        "owner": "pitchlog_owner",
        "enableRls": True,
        "forceRls": True,
        "appendOnly": True,
        "columns": [
            {
                "name": name,
                "sqlType": kind,
                "nullable": name == "reference_json",
                "default": "pg_catalog.clock_timestamp()"
                if name == "captured_at"
                else None,
            }
            for name, kind in _COLUMNS
        ],
        "primaryKey": [
            "tenant_id",
            "game_id",
            "internal_generation",
            "capsule_id",
            "d1",
        ],
        "foreignKeys": [
            {
                "columns": [
                    "tenant_id",
                    "game_id",
                    "internal_generation",
                    "capsule_id",
                    "d1",
                ],
                "target": "sync_fence.p3_projection_capsule_items",
                "targetColumns": [
                    "tenant_id",
                    "game_id",
                    "internal_generation",
                    "capsule_id",
                    "d1",
                ],
            },
            {
                "columns": ["tenant_id", "original_play_row_id"],
                "target": "public.play_rows",
                "targetColumns": ["tenant_id", "id"],
            },
            {
                "columns": ["tenant_id", "effective_play_row_id"],
                "target": "public.play_rows",
                "targetColumns": ["tenant_id", "id"],
            },
            {
                "columns": ["tenant_id", "effective_event_id"],
                "target": "public.operation_events",
                "targetColumns": ["tenant_id", "id"],
            },
            {
                "columns": ["tenant_id", "game_id", "capsule_stats_version_id"],
                "target": "sync_fence.stats_fact_versions",
                "targetColumns": ["tenant_id", "game_id", "id"],
            },
        ],
        "checks": [
            "internal_generation > 0",
            "d1 > 0",
            "play_row_version > 0",
            "item_digest ~ '^[a-f0-9]{64}$'",
            "capsule_source_set_digest ~ '^[a-f0-9]{64}$'",
            "jsonb_typeof(plays_csv_json) = 'object'",
            "jsonb_typeof(full_innings_json) = 'array'",
            "jsonb_typeof(runner_rows_json) = 'array'",
            "reference_json IS NULL OR jsonb_typeof(reference_json) = 'object'",
        ],
        "tablePrivileges": {},
        "columnPrivileges": {
            _OWNER: {
                "SELECT": [name for name, _ in _COLUMNS],
                "INSERT": [name for name, _ in _COLUMNS if name != "captured_at"],
            }
        },
        "policies": [
            {
                "role": _OWNER,
                "command": command,
                "tenantPredicate": (
                    "tenant_id = NULLIF(pg_catalog.current_setting("
                    "'app.tenant_id',true),'')::uuid"
                ),
            }
            for command in ("SELECT", "INSERT")
        ],
        "noDirectAppDml": True,
        "noDirectActorDml": True,
    }


def writer_source_query(root: Path = _ROOT) -> str:
    """唯一Sの既queryを保持し、同TXのcapsule/旧88列/訂正語彙だけを加える。"""
    profile = json.loads(
        (root / "backend/tests/fixtures/play_export_p3_selector_v2.json").read_bytes()
    )
    source_query, _ = candidate_read_bundle(root, p3_selector_profile=profile)
    if not source_query.endswith(";\n"):
        raise ValueError("P3 CSVの唯一S queryが不正")
    # readonly既関数をwriterで呼ぶのではなく、同じ生成queryを専用境界内で使う。
    return (
        "WITH selected_sources AS (\n"
        + source_query[:-2]
        + "\n)\n"
        + """SELECT s.fact_version_id,s.revision,s.source_set_sha256,s.source_count,
 s.completion_state,CAST(:transaction_id AS text) AS transaction_id,
 s.recording_generation,s.d1,s.d2,s.source_event_id,s.play_row_id,
 s.slot_version,s.play_row_version,s.base_event_id,s.source_fingerprint,
 c.id AS capsule_id,c.source_set_digest AS capsule_source_set_digest,
 c.stats_version_id AS capsule_stats_version_id,c.target_d1,c.watermark,
 i.item_digest,i.original_play_row_id,i.original_event_id,i.state,
 i.original_payload,i.original_history_entry,i.original_play_row,i.original_play_runners,
 i.payload,i.history_entry,i.play_row,i.play_runners,
 CASE WHEN prior_cap.id IS NOT NULL AND s.d1<=prior_cap.watermark
 THEN prior_csv.plays_csv_json ELSE original.plays_csv_json END AS original_csv_json,
 CASE WHEN prior_cap.id IS NOT NULL AND s.d1<=prior_cap.watermark
 THEN prior_csv.play_row_version ELSE original.play_version END
 AS original_snapshot_play_version,
 CASE WHEN prior_cap.id IS NOT NULL AND s.d1<=prior_cap.watermark
 THEN prior_csv.effective_event_id ELSE original.source_event_id END
 AS original_snapshot_source_event_id,
 CASE WHEN prior_cap.id IS NOT NULL AND s.d1<=prior_cap.watermark
 THEN prior_csv.internal_generation ELSE original.recording_generation END
 AS original_snapshot_generation,
 CASE WHEN prior_cap.id IS NOT NULL AND s.d1<=prior_cap.watermark
 THEN prior_item.d2 ELSE original.event_sequence END AS original_snapshot_sequence,
 v.key AS replacement_key,v.display_name AS replacement_label,
 pg_catalog.clock_timestamp() AS reference_captured_at,
 pg_catalog.gen_random_uuid() AS reference_id
FROM selected_sources s
JOIN sync_fence.p3_projection_heads h
 ON (h.tenant_id,h.game_id,h.internal_generation)
   =(:tenant_id,:game_id,s.recording_generation)
JOIN sync_fence.p3_projection_capsules c
 ON (c.tenant_id,c.game_id,c.internal_generation,c.id)
   =(h.tenant_id,h.game_id,h.internal_generation,h.capsule_id)
JOIN sync_fence.p3_projection_capsule_items i
 ON (i.tenant_id,i.game_id,i.internal_generation,i.capsule_id,i.d1,
     i.effective_event_id,i.effective_play_row_id)
   =(h.tenant_id,h.game_id,h.internal_generation,c.id,s.d1,s.source_event_id,s.play_row_id)
LEFT JOIN sync_fence.p3_projection_capsules prior_cap
 ON (prior_cap.tenant_id,prior_cap.game_id,prior_cap.internal_generation,prior_cap.id)
   =(h.tenant_id,h.game_id,h.internal_generation,:prior_capsule_id)
LEFT JOIN sync_fence.p3_projection_capsule_items prior_item
 ON (prior_item.tenant_id,prior_item.game_id,prior_item.internal_generation,
     prior_item.capsule_id,prior_item.d1,prior_item.effective_event_id,
     prior_item.effective_play_row_id)
   =(h.tenant_id,h.game_id,h.internal_generation,prior_cap.id,s.d1,
     i.original_event_id,i.original_play_row_id)
 AND prior_item.payload=i.original_payload
 AND prior_item.history_entry=i.original_history_entry
 AND prior_item.play_row=i.original_play_row
 AND prior_item.play_runners=i.original_play_runners
LEFT JOIN sync_fence.play_export_p3_snapshots prior_csv
 ON (prior_csv.tenant_id,prior_csv.game_id,prior_csv.internal_generation,
     prior_csv.capsule_id,prior_csv.d1,prior_csv.item_digest,
     prior_csv.effective_event_id,prior_csv.effective_play_row_id)
   =(h.tenant_id,h.game_id,h.internal_generation,prior_cap.id,s.d1,
     prior_item.item_digest,prior_item.effective_event_id,
     prior_item.effective_play_row_id)
LEFT JOIN public.operation_events original_event
 ON (original_event.tenant_id,original_event.game_id,original_event.id)
   =(h.tenant_id,h.game_id,i.original_event_id)
 AND original_event.payload=i.original_payload
LEFT JOIN public.play_export_snapshots original
 ON (original.tenant_id,original.game_id,original.play_row_id,
     original.source_event_id)
   =(h.tenant_id,h.game_id,i.original_play_row_id,original_event.id)
 AND (:prior_capsule_id IS NULL OR s.d1>prior_cap.watermark)
LEFT JOIN public.admin_vocabularies v
 ON i.d1=c.target_d1 AND v.key=i.play_row->>'batting_result_key'
 AND v.category='batting_result' AND NOT v.disabled
WHERE c.id=:capsule_id AND c.change_event_id=:change_event_id
 AND c.xmin::text::numeric
   =pg_catalog.mod(CAST(:transaction_id AS numeric),4294967296::numeric)
 AND c.stats_version_id=s.fact_version_id AND s.d1<=c.watermark
ORDER BY s.recording_generation,s.d1;
"""
    )


def writer_score_query(root: Path = _ROOT) -> str:
    """集計3列は旧writerと同じ唯一生成器へ委ね、別SQLを実装しない。"""
    profile = json.loads(
        (root / "backend/tests/fixtures/play_export_p3_selector_v2.json").read_bytes()
    )
    query, _ = generate_play_export_score_bundle(root, p3_selector_profile=profile)
    return _bound_generated_query(query)


def overlay_read_query() -> str:
    """同RRで既Sが選んだidentityにだけ現在capsule完成値を結ぶ候補。"""
    return f"""SELECT x.* FROM {_TABLE} x
JOIN sync_fence.p3_projection_heads h
 ON (h.tenant_id,h.game_id,h.internal_generation,h.capsule_id)
   =(x.tenant_id,x.game_id,x.internal_generation,x.capsule_id)
JOIN sync_fence.p3_projection_capsules c
 ON (c.tenant_id,c.game_id,c.internal_generation,c.id,
     c.source_set_digest,c.stats_version_id)
   =(x.tenant_id,x.game_id,x.internal_generation,x.capsule_id,
     x.capsule_source_set_digest,x.capsule_stats_version_id)
JOIN sync_fence.p3_projection_capsule_items i
 ON (i.tenant_id,i.game_id,i.internal_generation,i.capsule_id,i.d1,
     i.effective_event_id,i.effective_play_row_id,i.item_digest)
   =(x.tenant_id,x.game_id,x.internal_generation,x.capsule_id,x.d1,
     x.effective_event_id,x.effective_play_row_id,x.item_digest)
WHERE x.tenant_id=:tenant_id AND x.game_id=:game_id
 AND (x.internal_generation,x.d1) IN :qualified_source_positions
ORDER BY x.internal_generation,x.d1;
"""


_WRITER_OUTPUTS = (
    ("fact_version_id", "uuid"),
    ("revision", "bigint"),
    ("source_set_sha256", "text"),
    ("source_count", "bigint"),
    ("completion_state", "text"),
    ("transaction_id", "text"),
    ("recording_generation", "bigint"),
    ("d1", "bigint"),
    ("d2", "bigint"),
    ("source_event_id", "uuid"),
    ("play_row_id", "uuid"),
    ("slot_version", "bigint"),
    ("play_row_version", "bigint"),
    ("base_event_id", "uuid"),
    ("source_fingerprint", "text"),
    ("capsule_id", "uuid"),
    ("capsule_source_set_digest", "text"),
    ("capsule_stats_version_id", "uuid"),
    ("target_d1", "bigint"),
    ("watermark", "bigint"),
    ("item_digest", "text"),
    ("original_play_row_id", "uuid"),
    ("original_event_id", "uuid"),
    ("state", "text"),
    ("original_payload", "jsonb"),
    ("original_history_entry", "jsonb"),
    ("original_play_row", "jsonb"),
    ("original_play_runners", "jsonb"),
    ("payload", "jsonb"),
    ("history_entry", "jsonb"),
    ("play_row", "jsonb"),
    ("play_runners", "jsonb"),
    ("original_csv_json", "jsonb"),
    ("original_snapshot_play_version", "bigint"),
    ("original_snapshot_source_event_id", "uuid"),
    ("original_snapshot_generation", "bigint"),
    ("original_snapshot_sequence", "bigint"),
    ("replacement_key", "text"),
    ("replacement_label", "text"),
    ("reference_captured_at", "timestamp with time zone"),
    ("reference_id", "uuid"),
)


def _writer_bound_query(root: Path) -> str:
    """固定bindだけを変数へ写し、SQL literal/唯一Sの条件を変更しない。"""
    import re

    source = writer_source_query(root)
    mapping = {
        "tenant_id": "tenant",
        "game_id": "p_game_id",
        "model_sha256": "model_hash",
        "after_generation": "after_generation",
        "after_d1": "p_after_d1",
        "page_size": "p_page_size",
        "capsule_id": "p_capsule_id",
        "change_event_id": "p_change_event_id",
        "transaction_id": "own_xid",
        "prior_capsule_id": "p_prior_capsule_id",
    }
    seen = set()

    def replace(match):
        if match[1] is None:
            return match[0]
        name = match[1]
        if name not in mapping:
            raise ValueError("P3 CSV writer queryの未知bind")
        seen.add(name)
        return mapping[name]

    result = re.sub(r"'(?:''|[^'])*'|(?<!:):([a-z][a-z0-9_]*)", replace, source)
    if seen != set(mapping) or not result.endswith(";\n"):
        raise ValueError("P3 CSV writer queryのbind集合不一致")
    return result.rstrip().rstrip(";")


def candidate_writer_read_body(root: Path = _ROOT) -> str:
    """実writer/新capsuleを同xidで確認する私有読取候補。ACLはroot受理対象。"""
    from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

    outputs = ",\n ".join(f"{name} {kind}" for name, kind in _WRITER_OUTPUTS)
    query = _writer_bound_query(root)
    return f"""CREATE FUNCTION stats_api.read_writer_p3_play_export_page(
 p_attempt_id uuid,p_phase_id uuid,p_game_id uuid,p_capsule_id uuid,
 p_change_event_id uuid,p_after_d1 bigint,p_page_size integer,p_binding_nonce bytea,
 p_prior_capsule_id uuid,p_prior_native_version_id uuid,p_prior_checkpoint_id uuid,
 p_prior_checkpoint_revision bigint,p_prior_checkpoint_digest text)
RETURNS TABLE({outputs})
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_csv_read$
#variable_conflict use_column
DECLARE tenant uuid; own_xid text; generation bigint; target bigint;
 watermark_bound bigint; after_generation bigint; binding_device uuid;
 binding_d5 uuid; model_hash text := '{SOURCE_MODEL_HASH}';
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 IF session_user IS DISTINCT FROM 'pitchlog_app'
 OR current_user IS DISTINCT FROM '{_OWNER}' OR tenant IS NULL
 OR p_attempt_id IS NULL OR p_phase_id IS NULL OR p_game_id IS NULL
 OR p_capsule_id IS NULL OR p_change_event_id IS NULL
 OR p_after_d1 IS NULL OR p_after_d1<0
 OR p_page_size IS NULL OR p_page_size<1 OR p_page_size>25
 OR p_binding_nonce IS NULL OR pg_catalog.octet_length(p_binding_nonce)<>32
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'off'
 THEN RAISE EXCEPTION 'P3 CSV writer source unavailable'
 USING ERRCODE='42501'; END IF;
 SELECT b.device_id,b.internal_generation,b.d5
 INTO STRICT binding_device,generation,binding_d5
 FROM sync_fence.writer_bindings b
 WHERE (b.tenant_id,b.game_id,b.attempt_id,b.phase_id)
 =(tenant,p_game_id,p_attempt_id,p_phase_id)
 AND b.state='open' AND b.transaction_id=own_xid
 AND b.expires_at>pg_catalog.clock_timestamp();
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,binding_device,p_game_id);
 SELECT c.target_d1,c.watermark INTO STRICT target,watermark_bound
 FROM sync_fence.p3_projection_capsules c
 JOIN sync_fence.p3_projection_heads h
 ON (h.tenant_id,h.game_id,h.internal_generation,h.capsule_id)
 =(c.tenant_id,c.game_id,c.internal_generation,c.id)
 JOIN public.operation_events e ON (e.tenant_id,e.game_id,e.id)
 =(c.tenant_id,c.game_id,c.change_event_id)
 WHERE (c.tenant_id,c.game_id,c.internal_generation,c.id,c.change_event_id)
 =(tenant,p_game_id,generation,p_capsule_id,p_change_event_id)
 AND c.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND e.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND e.event_kind='play_change' AND e.ledger_kind='accepted'
 AND e.d5=binding_d5 AND NOT e.is_tombstone
 AND e.retired_at IS NULL AND e.replaced_at IS NULL;
 IF p_after_d1>=watermark_bound THEN
 RAISE EXCEPTION 'P3 CSV writer page unavailable' USING ERRCODE='42501'; END IF;
 IF p_prior_native_version_id IS NULL OR p_prior_checkpoint_id IS NULL
 OR p_prior_checkpoint_revision IS NULL OR p_prior_checkpoint_digest IS NULL
 OR NOT EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions old
 WHERE (old.tenant_id,old.game_id,old.id)
 =(tenant,p_game_id,p_prior_native_version_id)
 AND NOT old.is_current AND old.invalidated_at IS NOT NULL
 AND old.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric))
 OR NOT EXISTS(SELECT 1 FROM sync_fence.p3_projection_capsules actual
 WHERE (actual.tenant_id,actual.game_id,actual.internal_generation,actual.id,
        actual.prior_checkpoint_id,actual.prior_checkpoint_revision,
        actual.prior_checkpoint_digest)
 =(tenant,p_game_id,generation,p_capsule_id,p_prior_checkpoint_id,
   p_prior_checkpoint_revision,p_prior_checkpoint_digest))
 OR (p_prior_capsule_id IS NOT NULL AND NOT EXISTS(
 SELECT 1 FROM sync_fence.p3_projection_capsules prior
 WHERE (prior.tenant_id,prior.game_id,prior.internal_generation,prior.id)
 =(tenant,p_game_id,generation,p_prior_capsule_id))) THEN
 RAISE EXCEPTION 'P3 CSV prior source unavailable' USING ERRCODE='42501'; END IF;
 after_generation:=CASE WHEN p_after_d1=0 THEN NULL ELSE generation END;
 RETURN QUERY {query};
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,binding_device,p_game_id);
END;
$p3_csv_read$;
"""


def candidate_prior_read_body(root: Path = _ROOT) -> str:
    """旧headを保存前だけに固定し、current native版をP3headの版と混同しない。"""
    import re

    from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

    profile = json.loads(
        (root / "backend/tests/fixtures/play_export_p3_selector_v2.json").read_bytes()
    )
    query, _ = candidate_read_bundle(root, p3_selector_profile=profile)
    names = {
        "tenant_id": "tenant",
        "game_id": "p_game_id",
        "model_sha256": "model_hash",
        "after_generation": "NULL::bigint",
        "after_d1": "NULL::bigint",
        "page_size": "1",
    }
    seen = set()

    def replace(match):
        if match[1] is None:
            return match[0]
        if match[1] not in names:
            raise ValueError("P3 CSV前版queryの未知bind")
        seen.add(match[1])
        return names[match[1]]

    query = re.sub(r"'(?:''|[^'])*'|(?<!:):([a-z][a-z0-9_]*)", replace, query)
    if seen != set(names) or not query.endswith(";\n"):
        raise ValueError("P3 CSV前版queryのbind集合不一致")
    query = query[:-2]
    return f"""CREATE FUNCTION stats_api.read_writer_p3_play_export_prior(
 p_attempt_id uuid,p_phase_id uuid,p_game_id uuid,p_capsule_id uuid,
 p_change_event_id uuid,p_binding_nonce bytea,p_checkpoint_id uuid,
 p_checkpoint_revision bigint,p_checkpoint_digest text,p_watermark bigint)
RETURNS TABLE(prior_capsule_id uuid,prior_native_version_id uuid,
 prior_checkpoint_id uuid,prior_checkpoint_revision bigint,
 prior_checkpoint_digest text,transaction_id text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_csv_prior$
#variable_conflict use_column
DECLARE tenant uuid; own_xid text; binding_device uuid; generation bigint;
 model_hash text := '{SOURCE_MODEL_HASH}';
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 IF session_user IS DISTINCT FROM 'pitchlog_app'
 OR current_user IS DISTINCT FROM '{_OWNER}' OR tenant IS NULL
 OR p_attempt_id IS NULL OR p_phase_id IS NULL OR p_game_id IS NULL
 OR p_capsule_id IS NULL OR p_change_event_id IS NULL
 OR p_checkpoint_id IS NULL OR p_checkpoint_revision IS NULL
 OR p_checkpoint_revision<1 OR p_checkpoint_digest IS NULL
 OR p_checkpoint_digest !~ '^[a-f0-9]{{64}}$' OR p_watermark IS NULL OR p_watermark<1
 OR p_binding_nonce IS NULL OR pg_catalog.octet_length(p_binding_nonce)<>32
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'off'
 THEN RAISE EXCEPTION 'P3 CSV prior source unavailable' USING ERRCODE='42501'; END IF;
 SELECT b.device_id,b.internal_generation INTO STRICT binding_device,generation
 FROM sync_fence.writer_bindings b
 WHERE (b.tenant_id,b.game_id,b.attempt_id,b.phase_id)
 =(tenant,p_game_id,p_attempt_id,p_phase_id)
 AND b.state='open' AND b.transaction_id=own_xid
 AND b.expires_at>pg_catalog.clock_timestamp();
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,binding_device,p_game_id);
 IF EXISTS(SELECT 1 FROM sync_fence.p3_projection_capsules c
 WHERE (c.tenant_id,c.game_id,c.internal_generation,c.id)
 =(tenant,p_game_id,generation,p_capsule_id)) THEN
 RAISE EXCEPTION 'P3 CSV prior source already published' USING ERRCODE='42501'; END IF;
 RETURN QUERY WITH actual_source AS ({query})
 SELECT h.capsule_id,s.fact_version_id,cp.id,cp.revision,cp.content_digest,own_xid
 FROM actual_source s
 JOIN sync_fence.ordinary_pitch_checkpoints cp
 ON (cp.tenant_id,cp.game_id,cp.id,cp.revision,cp.content_digest)
 =(tenant,p_game_id,p_checkpoint_id,p_checkpoint_revision,p_checkpoint_digest)
 LEFT JOIN sync_fence.p3_projection_heads h
 ON (h.tenant_id,h.game_id,h.internal_generation)=(tenant,p_game_id,generation)
 WHERE s.source_count=p_watermark;
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,binding_device,p_game_id);
END;
$p3_csv_prior$;
"""


def candidate_save_body(root: Path = _ROOT) -> str:
    """前版receiptで限定した原本をcarryし、suffixだけ唯一生成スコアへ結ぶ。"""
    from pitchlog.exports.play_rows import CSV_HEADERS
    from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

    headers = tuple(CSV_HEADERS["plays.csv"])
    if len(headers) != 88 or any("'" in name for name in headers):
        raise ValueError("P3 CSVの閉列が不正")
    aggregate_indices = {34, 86, 87}
    dynamic_indices = set(range(10, 20)) | {45, 61, 62, 72, 73, 74}
    direct = tuple(name for n, name in enumerate(headers) if n not in aggregate_indices)
    immutable = tuple(
        name
        for n, name in enumerate(headers)
        if n not in aggregate_indices | dynamic_indices
    )
    sql_names = ",".join("'" + name + "'" for name in sorted(direct))
    all_names = ",".join("'" + name + "'" for name in sorted(headers))
    immutable_names = ",".join("'" + name + "'" for name in immutable)
    score = writer_score_query(root)
    return f"""CREATE FUNCTION stats_api.save_writer_p3_play_export_snapshot(
 p_attempt_id uuid,p_phase_id uuid,p_game_id uuid,p_capsule_id uuid,p_d1 bigint,
 p_binding_nonce bytea,p_direct_json jsonb,p_prior_capsule_id uuid,
 p_prior_native_version_id uuid,p_prior_checkpoint_id uuid,
 p_prior_checkpoint_revision bigint,p_prior_checkpoint_digest text)
RETURNS TABLE(saved_play_row_id uuid,saved_d1 bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_csv_save$
#variable_conflict use_column
DECLARE ctx record; own_xid text; change_id uuid; binding_device uuid;
 target bigint; expected_count integer; inserted_count integer;
 finished_json jsonb; full_json jsonb; references_json jsonb; field text;
 score_pitch bigint; score_top jsonb; score_bottom jsonb; score_full jsonb;
 tenant uuid; p_source_event_id uuid; p_fact_version_id uuid;
 p_source_set_sha256 text; p_revision bigint;
 model_hash text := '{SOURCE_MODEL_HASH}';
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 IF session_user IS DISTINCT FROM 'pitchlog_app'
 OR current_user IS DISTINCT FROM '{_OWNER}' OR tenant IS NULL
 OR p_attempt_id IS NULL OR p_phase_id IS NULL OR p_game_id IS NULL
 OR p_capsule_id IS NULL OR p_d1 IS NULL OR p_d1<1
 OR p_binding_nonce IS NULL OR pg_catalog.octet_length(p_binding_nonce)<>32
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'off'
 THEN RAISE EXCEPTION 'P3 CSV save source unavailable' USING ERRCODE='42501'; END IF;
 SELECT c.change_event_id,c.target_d1 INTO STRICT change_id,target
 FROM sync_fence.p3_projection_capsules c
 WHERE (c.tenant_id,c.game_id,c.id)=(tenant,p_game_id,p_capsule_id)
 AND c.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric);
 IF p_direct_json IS NULL THEN
 IF p_d1>=target THEN
 RAISE EXCEPTION 'P3 CSV suffix requires direct projection' USING ERRCODE='42501';
 END IF;
 expected_count:=LEAST(25,target-p_d1)::integer;
 RETURN QUERY WITH candidates AS (
 SELECT x.*,CASE WHEN p_prior_capsule_id IS NOT NULL AND x.d1<=prior.watermark
 THEN old.full_innings_json ELSE normal.full_innings_json END AS old_innings
 FROM stats_api.read_writer_p3_play_export_page(
 p_attempt_id,p_phase_id,p_game_id,p_capsule_id,change_id,p_d1-1,
 expected_count,p_binding_nonce,p_prior_capsule_id,p_prior_native_version_id,
 p_prior_checkpoint_id,p_prior_checkpoint_revision,p_prior_checkpoint_digest) x
 LEFT JOIN sync_fence.p3_projection_capsules prior
 ON (prior.tenant_id,prior.game_id,prior.internal_generation,prior.id)
 =(tenant,p_game_id,x.recording_generation,p_prior_capsule_id)
 LEFT JOIN {_TABLE} old ON
 (old.tenant_id,old.game_id,old.internal_generation,old.capsule_id,old.d1)
 =(tenant,p_game_id,x.recording_generation,p_prior_capsule_id,x.d1)
 LEFT JOIN public.play_export_snapshots normal ON
 (normal.tenant_id,normal.game_id,normal.play_row_id)
 =(tenant,p_game_id,x.original_play_row_id)
 ), valid AS (
 SELECT x.* FROM candidates x WHERE x.d1>=p_d1 AND x.d1<target
 AND x.state='unchanged' AND x.original_payload=x.payload
 AND x.original_history_entry=x.history_entry
 AND x.original_play_row=x.play_row AND x.original_play_runners=x.play_runners
 AND x.original_snapshot_source_event_id=x.original_event_id
 AND x.original_snapshot_play_version=(x.original_play_row->>'version')::bigint
 AND x.original_snapshot_generation=x.recording_generation
 AND x.original_snapshot_sequence=x.d2
 AND pg_catalog.jsonb_typeof(x.original_csv_json)='object'
 AND (SELECT pg_catalog.array_agg(k ORDER BY k COLLATE "C")
 FROM pg_catalog.jsonb_object_keys(x.original_csv_json) k)=ARRAY[{all_names}]::text[]
 AND NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_each(x.original_csv_json) v
 WHERE pg_catalog.jsonb_typeof(v.value) NOT IN ('string','null'))
 AND pg_catalog.jsonb_typeof(x.old_innings)='array'
 ), inserted AS (INSERT INTO {_TABLE}(
 tenant_id,game_id,internal_generation,capsule_id,d1,original_play_row_id,
 effective_event_id,effective_play_row_id,play_row_version,item_digest,
 capsule_source_set_digest,capsule_stats_version_id,plays_csv_json,
 full_innings_json,runner_rows_json,reference_json)
 SELECT tenant,p_game_id,x.recording_generation,p_capsule_id,x.d1,
 x.original_play_row_id,x.source_event_id,x.play_row_id,x.play_row_version,
 x.item_digest,x.capsule_source_set_digest,x.capsule_stats_version_id,
 x.original_csv_json,x.old_innings,x.play_runners,
 pg_catalog.jsonb_build_object('formatVersion','p3-csv-references-v1',
 'priorCapsuleId',p_prior_capsule_id,'priorNativeVersionId',p_prior_native_version_id,
 'priorCheckpoint',pg_catalog.jsonb_build_object('id',p_prior_checkpoint_id,
 'revision',p_prior_checkpoint_revision,'digest',p_prior_checkpoint_digest),
 'replacementResult',NULL)
 FROM valid x ORDER BY x.d1
 RETURNING effective_play_row_id,d1)
 SELECT z.effective_play_row_id,z.d1 FROM inserted z ORDER BY z.d1;
 GET DIAGNOSTICS inserted_count=ROW_COUNT;
 IF inserted_count IS DISTINCT FROM expected_count THEN
 RAISE EXCEPTION 'P3 CSV carry coverage missing' USING ERRCODE='42501'; END IF;
 SELECT b.device_id INTO STRICT binding_device FROM sync_fence.writer_bindings b
 WHERE (b.tenant_id,b.game_id,b.attempt_id,b.phase_id)
 =(tenant,p_game_id,p_attempt_id,p_phase_id) AND b.state='open'
 AND b.transaction_id=own_xid;
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,binding_device,p_game_id);
 RETURN;
 END IF;
 SELECT * INTO STRICT ctx FROM stats_api.read_writer_p3_play_export_page(
 p_attempt_id,p_phase_id,p_game_id,p_capsule_id,change_id,p_d1-1,1,p_binding_nonce,
 p_prior_capsule_id,p_prior_native_version_id,p_prior_checkpoint_id,
 p_prior_checkpoint_revision,p_prior_checkpoint_digest);
 IF ctx.d1 IS DISTINCT FROM p_d1
 OR pg_catalog.jsonb_typeof(ctx.original_csv_json) IS DISTINCT FROM 'object'
 OR (SELECT pg_catalog.array_agg(k ORDER BY k COLLATE "C")
 FROM pg_catalog.jsonb_object_keys(ctx.original_csv_json) k)
 IS DISTINCT FROM ARRAY[{all_names}]::text[]
 OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_each(ctx.original_csv_json) v
 WHERE pg_catalog.jsonb_typeof(v.value) NOT IN ('string','null'))
 OR ctx.original_snapshot_source_event_id IS DISTINCT FROM ctx.original_event_id
 OR ctx.original_snapshot_play_version IS DISTINCT FROM
 (ctx.original_play_row->>'version')::bigint
 OR ctx.original_snapshot_generation IS DISTINCT FROM ctx.recording_generation
 OR ctx.original_snapshot_sequence IS DISTINCT FROM ctx.d2 THEN
 RAISE EXCEPTION 'P3 CSV original snapshot unavailable' USING ERRCODE='42501'; END IF;
 IF ctx.d1<ctx.target_d1 THEN
 IF p_direct_json IS NOT NULL OR ctx.state IS DISTINCT FROM 'unchanged'
 OR ctx.original_payload IS DISTINCT FROM ctx.payload
 OR ctx.original_history_entry IS DISTINCT FROM ctx.history_entry
 OR ctx.original_play_row IS DISTINCT FROM ctx.play_row
 OR ctx.original_play_runners IS DISTINCT FROM ctx.play_runners THEN
 RAISE EXCEPTION 'P3 CSV prefix carry rejected' USING ERRCODE='42501'; END IF;
 finished_json:=ctx.original_csv_json;
 SELECT CASE WHEN p_prior_capsule_id IS NOT NULL AND ctx.d1<=c.watermark
 THEN old.full_innings_json ELSE normal.full_innings_json END INTO STRICT full_json
 FROM (SELECT 1) one
 LEFT JOIN sync_fence.p3_projection_capsules c
 ON (c.tenant_id,c.game_id,c.id)=(tenant,p_game_id,p_prior_capsule_id)
 LEFT JOIN {_TABLE} old ON
 (old.tenant_id,old.game_id,old.internal_generation,old.capsule_id,old.d1)
 =(tenant,p_game_id,ctx.recording_generation,p_prior_capsule_id,ctx.d1)
 LEFT JOIN public.play_export_snapshots normal ON
 (normal.tenant_id,normal.game_id,normal.play_row_id)
 =(tenant,p_game_id,ctx.original_play_row_id);
 ELSE
 IF pg_catalog.jsonb_typeof(p_direct_json) IS DISTINCT FROM 'object'
 OR (SELECT pg_catalog.array_agg(key ORDER BY key COLLATE "C")
 FROM pg_catalog.jsonb_object_keys(p_direct_json) key)
 IS DISTINCT FROM ARRAY[{sql_names}]::text[]
 OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_each(p_direct_json) value
 WHERE pg_catalog.jsonb_typeof(value.value) NOT IN ('string','null')) THEN
 RAISE EXCEPTION 'P3 CSV direct columns rejected' USING ERRCODE='42501'; END IF;
 FOREACH field IN ARRAY ARRAY[{immutable_names}]::text[] LOOP
 IF p_direct_json->field IS DISTINCT FROM ctx.original_csv_json->field THEN
 RAISE EXCEPTION 'P3 CSV recorded reference changed' USING ERRCODE='42501'; END IF;
 END LOOP;
 IF ctx.d1=ctx.target_d1 AND (ctx.replacement_key NOT IN
 ('batting-result.ball','batting-result.called-strike')
 OR ctx.replacement_label IS NULL
 OR p_direct_json->>'{headers[45]}' IS DISTINCT FROM ctx.replacement_label) THEN
 RAISE EXCEPTION 'P3 CSV replacement reference unavailable'
 USING ERRCODE='42501'; END IF;
 IF ctx.d1<>ctx.target_d1 AND p_direct_json->'{headers[45]}'
 IS DISTINCT FROM ctx.original_csv_json->'{headers[45]}' THEN
 RAISE EXCEPTION 'P3 CSV follower reference changed' USING ERRCODE='42501'; END IF;
 p_source_event_id:=ctx.source_event_id; p_fact_version_id:=ctx.fact_version_id;
 p_source_set_sha256:=ctx.source_set_sha256; p_revision:=ctx.revision;
 SELECT s.pitcher_pitch_count,s.top_score,s.bottom_score,s.full_innings
 INTO STRICT score_pitch,score_top,score_bottom,score_full FROM ({score}) s;
 IF score_pitch IS NULL OR score_top IS NULL OR score_bottom IS NULL
 OR score_full IS NULL THEN
 RAISE EXCEPTION 'P3 CSV generated score unavailable' USING ERRCODE='22023'; END IF;
 finished_json:=p_direct_json || pg_catalog.jsonb_build_object(
 '{headers[34]}',score_pitch::text,'{headers[86]}',score_top::text,
 '{headers[87]}',score_bottom::text);
 full_json:=score_full;
 END IF;
 IF pg_catalog.jsonb_typeof(full_json) IS DISTINCT FROM 'array' THEN
 RAISE EXCEPTION 'P3 CSV completed innings unavailable' USING ERRCODE='42501'; END IF;
 references_json:=pg_catalog.jsonb_build_object(
 'formatVersion','p3-csv-references-v1','priorCapsuleId',p_prior_capsule_id,
 'priorNativeVersionId',p_prior_native_version_id,
 'priorCheckpoint',pg_catalog.jsonb_build_object('id',p_prior_checkpoint_id,
 'revision',p_prior_checkpoint_revision,'digest',p_prior_checkpoint_digest),
 'replacementResult',CASE WHEN ctx.d1=ctx.target_d1 THEN
 pg_catalog.jsonb_build_object('id',ctx.reference_id,'key',ctx.replacement_key,
 'displayName',ctx.replacement_label,'capturedAt',ctx.reference_captured_at,
 'capsuleId',ctx.capsule_id,'effectiveEventId',ctx.source_event_id) ELSE NULL END);
 INSERT INTO {_TABLE}(
 tenant_id,game_id,internal_generation,capsule_id,d1,original_play_row_id,
 effective_event_id,effective_play_row_id,play_row_version,item_digest,
 capsule_source_set_digest,capsule_stats_version_id,plays_csv_json,
 full_innings_json,runner_rows_json,reference_json)
 VALUES(tenant,p_game_id,ctx.recording_generation,p_capsule_id,ctx.d1,
 ctx.original_play_row_id,ctx.source_event_id,ctx.play_row_id,ctx.play_row_version,
 ctx.item_digest,ctx.capsule_source_set_digest,ctx.capsule_stats_version_id,
 finished_json,full_json,ctx.play_runners,references_json);
 SELECT b.device_id INTO STRICT binding_device FROM sync_fence.writer_bindings b
 WHERE (b.tenant_id,b.game_id,b.attempt_id,b.phase_id)
 =(tenant,p_game_id,p_attempt_id,p_phase_id) AND b.state='open'
 AND b.transaction_id=own_xid;
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,binding_device,p_game_id);
 RETURN QUERY SELECT ctx.play_row_id,ctx.d1;
END;
$p3_csv_save$;
"""
