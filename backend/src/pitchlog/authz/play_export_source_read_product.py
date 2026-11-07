"""唯一の生成Sを再利用するCSV source identity読取候補。製品登録前。"""

import re
from pathlib import Path

from pitchlog.authz.stats_primitive_sql import _verified_inputs
from pitchlog.domaingen.play_export_score import _canonical_parts
from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

_ROOT = Path(__file__).resolve().parents[4]


def candidate_read_bundle(root: Path = _ROOT) -> tuple[str, str]:
    """検証済みの唯一Sを同RRの有限identity読取へ束縛する。"""
    _, sections, _, _ = _verified_inputs(root)
    prefix, members = _canonical_parts(sections)
    if members.count("s.fact_version_id=:fact_version_id") != 1:
        raise ValueError("唯一Sの会員版束縛位置が不正")
    query = (
        prefix
        + """, version_scope AS (
 SELECT v.* FROM sync_fence.stats_fact_versions v
 JOIN canonical_health h ON (h.tenant_id,h.game_id)=(v.tenant_id,v.game_id)
 WHERE v.tenant_id=:tenant_id AND v.game_id=:game_id
   AND v.model_sha256=:model_sha256 AND v.is_current AND v.invalidated_at IS NULL
   AND v.completion_state IN ('current_open','confirmed_ended')
   AND h.game_count=1 AND h.unavailable_count=0
   AND h.canonical_source_count=v.source_count
   AND h.canonical_source_set_sha256=v.source_set_sha256
), candidate_members AS (
"""
        + members.replace(
            "s.fact_version_id=:fact_version_id",
            "s.fact_version_id=(SELECT id FROM version_scope)",
        )
        + """
), source_members AS (
 SELECT s.* FROM candidate_members s JOIN version_scope v
   ON (v.tenant_id,v.game_id,v.id)=(s.tenant_id,s.game_id,s.fact_version_id)
), member_health AS (
 SELECT v.id,COUNT(s.source_event_id) AS actual_count,v.source_count
 FROM version_scope v LEFT JOIN source_members s
   ON (s.tenant_id,s.game_id,s.fact_version_id)=(v.tenant_id,v.game_id,v.id)
 GROUP BY v.id,v.source_count
), bounded_members AS (
 SELECT s.*,c.base_event_id FROM source_members s JOIN canonical_s c
   ON (c.tenant_id,c.game_id,c.recording_generation,c.d1,c.source_event_id,
       c.slot_version,c.play_row_id,c.play_row_version)
    =(s.tenant_id,s.game_id,s.recording_generation,s.d1,s.source_event_id,
       s.slot_version,s.play_row_id,s.play_row_version)
 WHERE (:after_generation IS NULL OR
       (s.recording_generation,s.d1)>(:after_generation,:after_d1))
 ORDER BY s.recording_generation,s.d1 LIMIT :page_size
)
SELECT v.id AS fact_version_id,v.revision,v.source_set_sha256,v.source_count,
 v.completion_state,pg_catalog.pg_current_snapshot()::text AS transaction_id,
 s.recording_generation,s.d1,s.d2,s.source_event_id,s.play_row_id,
 s.slot_version,s.play_row_version,s.base_event_id,s.source_fingerprint
FROM version_scope v JOIN member_health h ON h.id=v.id
LEFT JOIN bounded_members s ON true
WHERE h.actual_count=h.source_count
ORDER BY s.recording_generation,s.d1;
"""
    )
    # 生成selectorの会員条件は唯一の既原典をそのまま用い、版参照だけ束縛する。
    binds = {
        "tenant_id": "tenant",
        "game_id": "p_game_id",
        "model_sha256": "model_hash",
        "after_generation": "p_after_generation",
        "after_d1": "p_after_d1",
        "page_size": "p_page_size",
    }
    seen = set()

    def replace(match):
        if match[1] is None:
            return match[0]
        name = match[1]
        if name not in binds:
            raise ValueError("unknown bind")
        seen.add(name)
        return binds[name]

    bound = re.sub(r"'(?:''|[^'])*'|(?<!:):([a-z][a-z0-9_]*)", replace, query)
    if seen != set(binds):
        raise ValueError("bind set mismatch")
    body = f"""CREATE FUNCTION stats_api.read_play_export_source_page(
 p_game_id uuid,p_after_generation bigint,p_after_d1 bigint,p_page_size integer)
RETURNS TABLE(fact_version_id uuid,revision bigint,source_set_sha256 text,
 source_count bigint,completion_state text,transaction_id text,
 recording_generation bigint,d1 bigint,d2 bigint,source_event_id uuid,
 play_row_id uuid,slot_version bigint,play_row_version bigint,base_event_id uuid,
 source_fingerprint text)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $csv_sources$
#variable_conflict use_column
DECLARE tenant uuid; model_hash text:='{SOURCE_MODEL_HASH}';
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 IF session_user IS DISTINCT FROM 'pitchlog_app'
 OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'
 OR tenant IS NULL OR p_game_id IS NULL
 OR pg_catalog.current_setting('transaction_isolation')
   IS DISTINCT FROM 'repeatable read'
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'on'
 OR p_page_size IS NULL OR p_page_size<1 OR p_page_size>500
 OR NOT ((p_after_generation IS NULL AND p_after_d1 IS NULL)
   OR (p_after_generation IS NOT NULL AND p_after_generation>=1
       AND p_after_d1 IS NOT NULL AND p_after_d1>=1))
 THEN RAISE EXCEPTION 'play export source boundary rejected'
   USING ERRCODE='42501'; END IF;
 RETURN QUERY
 {bound}
 IF NOT FOUND THEN RAISE EXCEPTION 'play export source unavailable'
   USING ERRCODE='22023'; END IF;
END;
$csv_sources$;
"""
    identity = "stats_api.read_play_export_source_page(uuid,bigint,bigint,integer)"
    return (
        query,
        body + f"ALTER FUNCTION {identity} OWNER TO pitchlog_sync_right_fn_owner;\n"
        f"REVOKE ALL ON FUNCTION {identity} FROM PUBLIC,pitchlog_app;\n"
        f"GRANT EXECUTE ON FUNCTION {identity} TO pitchlog_app;\n",
    )
