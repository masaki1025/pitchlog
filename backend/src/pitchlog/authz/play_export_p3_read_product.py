"""P3 CSVの歴代完成原本を同RRの唯一S/headerへ結ぶ読取候補。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pitchlog.authz.play_export_p3_product import _COLUMNS
from pitchlog.authz.play_export_source_read_product import candidate_read_bundle
from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

_ROOT = Path(__file__).resolve().parents[4]


def candidate_read_body(root: Path = _ROOT) -> str:
    """自由JSON/任意queryを受けずtenant/gameと500keysetだけを受ける。"""
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
        name = match[1]
        if name not in names:
            raise ValueError("P3 CSV読取の唯一S bindが未知")
        seen.add(name)
        return names[name]

    query = re.sub(r"'(?:''|[^'])*'|(?<!:):([a-z][a-z0-9_]*)", replace, query)
    if seen != set(names) or not query.endswith(";\n"):
        raise ValueError("P3 CSV読取の唯一S bindが不足")
    source = query[:-2]
    columns = ",\n ".join(name + " " + kind for name, kind in _COLUMNS)
    fields = ",".join("x." + name for name, _ in _COLUMNS)
    return f"""CREATE FUNCTION stats_api.read_play_export_p3_snapshots(
 p_game_id uuid,p_after_generation bigint,p_after_capsule_id uuid,
 p_after_d1 bigint,p_page_size integer)
RETURNS TABLE(fact_version_id uuid,revision bigint,source_set_sha256 text,
 source_count bigint,completion_state text,transaction_id text,
 overlay_count bigint,{columns},capsule_watermark bigint,
 capsule_target_d1 bigint,current_head boolean,item_json jsonb)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_csv_snapshot_read$
#variable_conflict use_column
DECLARE tenant uuid; model_hash text := '{SOURCE_MODEL_HASH}';
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 IF session_user IS DISTINCT FROM 'pitchlog_app'
 OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'
 OR tenant IS NULL OR p_game_id IS NULL
 OR p_page_size IS NULL OR p_page_size<1 OR p_page_size>500
 OR pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM
 'repeatable read'
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'on'
 OR ((p_after_generation IS NULL OR p_after_capsule_id IS NULL OR p_after_d1 IS NULL)
 AND NOT(p_after_generation IS NULL AND p_after_capsule_id IS NULL
 AND p_after_d1 IS NULL))
 OR p_after_generation<1 OR p_after_d1<1 THEN
 RAISE EXCEPTION 'P3 CSV read scope unavailable' USING ERRCODE='42501'; END IF;
 RETURN QUERY WITH actual_source AS ({source}), health AS (
 SELECT COALESCE(SUM(c.watermark),0)::bigint AS overlay_count
 FROM sync_fence.p3_projection_capsules c
 WHERE (c.tenant_id,c.game_id)=(tenant,p_game_id)
 ), bounded AS (
 SELECT x.*,c.watermark AS capsule_watermark,c.target_d1 AS capsule_target_d1,
 COALESCE(h.capsule_id=x.capsule_id,false) AS current_head,
 pg_catalog.to_jsonb(i) AS item_json
 FROM sync_fence.play_export_p3_snapshots x
 JOIN sync_fence.p3_projection_capsules c ON
 (c.tenant_id,c.game_id,c.internal_generation,c.id,c.source_set_digest,
 c.stats_version_id)=(x.tenant_id,x.game_id,x.internal_generation,x.capsule_id,
 x.capsule_source_set_digest,x.capsule_stats_version_id)
 JOIN sync_fence.p3_projection_capsule_items i ON
 (i.tenant_id,i.game_id,i.internal_generation,i.capsule_id,i.d1,
 i.item_digest,i.original_play_row_id,i.effective_event_id,i.effective_play_row_id)
 =(x.tenant_id,x.game_id,x.internal_generation,x.capsule_id,x.d1,x.item_digest,
 x.original_play_row_id,x.effective_event_id,x.effective_play_row_id)
 LEFT JOIN sync_fence.p3_projection_heads h ON
 (h.tenant_id,h.game_id,h.internal_generation)
 =(x.tenant_id,x.game_id,x.internal_generation)
 CROSS JOIN actual_source s
 WHERE (x.tenant_id,x.game_id)=(tenant,p_game_id) AND x.d1<=c.watermark
 AND (p_after_generation IS NULL OR
 (x.internal_generation,x.capsule_id,x.d1)>
 (p_after_generation,p_after_capsule_id,p_after_d1))
 ORDER BY x.internal_generation,x.capsule_id,x.d1 LIMIT p_page_size
 ) SELECT s.fact_version_id,s.revision,s.source_set_sha256,s.source_count,
 s.completion_state,s.transaction_id,health.overlay_count,{fields},
 x.capsule_watermark,x.capsule_target_d1,x.current_head,x.item_json
 FROM actual_source s CROSS JOIN health LEFT JOIN bounded x ON true
 ORDER BY x.internal_generation,x.capsule_id,x.d1;
END;
$p3_csv_snapshot_read$;
"""
