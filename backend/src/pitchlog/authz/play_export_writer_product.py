"""毎球CSVの同TX限定D-1集計関数を候補として描画する。"""

from __future__ import annotations

import re

from pitchlog.domaingen.play_export_score import generate_play_export_score_bundle
from pitchlog.exports.play_rows import CSV_HEADERS
from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

_OWNER = "pitchlog_sync_right_fn_owner"
_APP = "pitchlog_app"
_NAME = "stats_api.read_writer_play_export_aggregate"
_ARGS = (
    "p_attempt_id uuid,p_phase_id uuid,p_source_event_id uuid,"
    "p_fact_version_id uuid,p_source_set_sha256 text,p_revision bigint,"
    "p_binding_nonce bytea"
)
_IDENTITY = "uuid,uuid,uuid,uuid,text,bigint,bytea"
_SAVE_NAME = "stats_api.save_writer_play_export_snapshot"
_SAVE_ARGS = _ARGS + ",p_direct_json jsonb"
_SAVE_IDENTITY = _IDENTITY + ",jsonb"
_BIND = {
    "tenant_id": "tenant",
    "game_id": "p_game_id",
    "fact_version_id": "p_fact_version_id",
    "source_set_sha256": "p_source_set_sha256",
    "revision": "p_revision",
    "model_sha256": "model_hash",
    "source_event_id": "p_source_event_id",
}


def _bound_generated_query(source: str) -> str:
    """文字列literalを保持し、既7つの生成bindだけをPL変数へ写す。"""
    if type(source) is not str or source.count("\nWITH canonical_scope AS (") != 1:
        raise ValueError("スコア生成SQLが不正")
    sql = (
        "WITH canonical_scope AS (" + source.split("\nWITH canonical_scope AS (", 1)[1]
    )
    observed: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        if match[1] is None:
            return match[0]
        name = match[1]
        if name not in _BIND:
            raise ValueError("未知のスコアSQL bind")
        observed.add(name)
        return _BIND[name]

    sql = re.sub(
        r"'(?:''|[^'])*'|(?<!:):([a-z][a-z0-9_]*)",
        replace,
        sql,
    )
    if observed != set(_BIND) or not sql.endswith(";\n"):
        raise ValueError("スコアSQL bind集合が不正")
    return sql.rstrip().rstrip(";")


def candidate_function_body() -> str:
    """既binding・source・xid・D5を同関数内で再確認する。"""
    target, _ = generate_play_export_score_bundle()
    query = _bound_generated_query(target)
    return f"""CREATE FUNCTION {_NAME}({_ARGS})
RETURNS TABLE(pitcher_pitch_count bigint,top_score jsonb,bottom_score jsonb,
  full_innings jsonb) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $export$
#variable_conflict use_column
DECLARE tenant uuid; own_xid text; p_game_id uuid;
  model_hash text := '{SOURCE_MODEL_HASH}';
  binding_device uuid; binding_generation bigint; binding_d5 uuid;
  event_accepted integer;
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 IF session_user IS DISTINCT FROM '{_APP}' OR current_user IS DISTINCT FROM '{_OWNER}'
   OR tenant IS NULL OR p_attempt_id IS NULL OR p_phase_id IS NULL
   OR p_source_event_id IS NULL OR p_fact_version_id IS NULL
   OR p_source_set_sha256 IS NULL OR p_source_set_sha256 !~ '^[a-f0-9]{{64}}$'
   OR p_revision IS NULL OR p_revision<1 OR p_binding_nonce IS NULL
   OR pg_catalog.octet_length(p_binding_nonce)<>32
   OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'off'
 THEN RAISE EXCEPTION 'play export writer boundary rejected'
   USING ERRCODE='42501'; END IF;
 SELECT b.game_id,b.device_id,b.internal_generation,b.d5
   INTO STRICT p_game_id,binding_device,binding_generation,binding_d5
 FROM sync_fence.writer_bindings b
 WHERE b.tenant_id=tenant AND b.attempt_id=p_attempt_id AND b.phase_id=p_phase_id
   AND b.state='open' AND b.transaction_id=own_xid
   AND b.expires_at>pg_catalog.clock_timestamp();
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
   p_binding_nonce,binding_device,p_game_id);
 SELECT 1 INTO STRICT event_accepted FROM public.operation_events e
 WHERE e.tenant_id=tenant AND e.game_id=p_game_id AND e.id=p_source_event_id
   AND e.generation=binding_generation AND e.d5=binding_d5
   AND e.event_kind='play_input' AND e.ledger_kind='accepted'
   AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
   AND e.import_batch_id IS NULL AND NOT e.migration_unverified
   AND e.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric);
 RETURN QUERY
 {query};
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
   p_binding_nonce,binding_device,p_game_id);
END;
$export$;
"""


def candidate_install_sql() -> str:
    """読取/保存2関数のowner/ACLを既統制と同型で描画する。"""
    identity = f"{_NAME}({_IDENTITY})"
    save_identity = f"{_SAVE_NAME}({_SAVE_IDENTITY})"
    return (
        candidate_function_body()
        + f"ALTER FUNCTION {identity} OWNER TO {_OWNER};\n"
        + f"REVOKE ALL ON FUNCTION {identity} FROM PUBLIC,{_APP};\n"
        + f"GRANT EXECUTE ON FUNCTION {identity} TO {_APP};\n"
        + candidate_save_body()
        + f"ALTER FUNCTION {save_identity} OWNER TO {_OWNER};\n"
        + f"REVOKE ALL ON FUNCTION {save_identity} FROM PUBLIC,{_APP};\n"
        + f"GRANT EXECUTE ON FUNCTION {save_identity} TO {_APP};\n"
    )


def candidate_save_body() -> str:
    """同じ真正writerと生成スコアを再照合して88列を一度だけ保存する。"""
    columns = tuple(CSV_HEADERS["plays.csv"])
    if len(columns) != 88 or len(set(columns)) != 88 or any("'" in n for n in columns):
        raise ValueError("毎球CSVの閉列が不正")
    direct = tuple(
        name for index, name in enumerate(columns) if index not in (34, 86, 87)
    )
    expected = ",".join("'" + name + "'" for name in direct)
    return f"""CREATE FUNCTION {_SAVE_NAME}({_SAVE_ARGS})
RETURNS uuid LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $export_save$
#variable_conflict use_column
DECLARE tenant uuid; own_xid text; bound_game uuid; bound_device uuid;
  bound_generation bigint; bound_d5 uuid; source_d2 bigint;
  saved_play uuid; saved_version bigint; direct_count bigint;
  score_pitch bigint; score_top jsonb; score_bottom jsonb; score_full jsonb;
  finished_json jsonb;
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 IF session_user IS DISTINCT FROM '{_APP}' OR current_user IS DISTINCT FROM '{_OWNER}'
   OR tenant IS NULL OR p_attempt_id IS NULL OR p_phase_id IS NULL
   OR p_source_event_id IS NULL OR p_fact_version_id IS NULL
   OR p_direct_json IS NULL OR pg_catalog.jsonb_typeof(p_direct_json)<>'object'
 THEN RAISE EXCEPTION 'play export save boundary rejected'
   USING ERRCODE='42501'; END IF;
 SELECT count(*) INTO direct_count FROM pg_catalog.jsonb_object_keys(p_direct_json);
 IF direct_count<>85 OR NOT (p_direct_json ?& ARRAY[{expected}]::text[])
 THEN RAISE EXCEPTION 'play export columns rejected' USING ERRCODE='22023'; END IF;
 SELECT b.game_id,b.device_id,b.internal_generation,b.d5
   INTO STRICT bound_game,bound_device,bound_generation,bound_d5
 FROM sync_fence.writer_bindings b
 WHERE b.tenant_id=tenant AND b.attempt_id=p_attempt_id AND b.phase_id=p_phase_id
   AND b.state='open' AND b.transaction_id=own_xid
   AND b.expires_at>pg_catalog.clock_timestamp();
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
   p_binding_nonce,bound_device,bound_game);
 SELECT e.d2 INTO STRICT source_d2 FROM public.operation_events e
 WHERE e.tenant_id=tenant AND e.game_id=bound_game AND e.id=p_source_event_id
   AND e.generation=bound_generation AND e.d5=bound_d5
   AND e.event_kind='play_input' AND e.ledger_kind='accepted'
   AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
   AND e.import_batch_id IS NULL AND NOT e.migration_unverified
   AND e.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric);
 SELECT p.id,p.version INTO STRICT saved_play,saved_version FROM public.play_rows p
 WHERE p.tenant_id=tenant AND p.game_id=bound_game
   AND p.source_event_id=p_source_event_id
   AND p.event_kind IN ('pitch','non_pitch')
   AND p.hidden_at IS NULL AND p.version=1
   AND p.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric);
 SELECT s.pitcher_pitch_count,s.top_score,s.bottom_score,s.full_innings
 INTO STRICT score_pitch,score_top,score_bottom,score_full
 FROM {_NAME}(p_attempt_id,p_phase_id,p_source_event_id,p_fact_version_id,
   p_source_set_sha256,p_revision,p_binding_nonce) s;
 IF score_pitch IS NULL OR score_top IS NULL OR score_bottom IS NULL
   OR score_full IS NULL OR source_d2 IS NULL
 THEN RAISE EXCEPTION 'play export score unavailable' USING ERRCODE='22023'; END IF;
 finished_json:=p_direct_json || pg_catalog.jsonb_build_object(
   '球数',score_pitch::text,'top_score',score_top::text,
   'bottom_score',score_bottom::text);
 INSERT INTO public.play_export_snapshots(
   tenant_id,game_id,play_row_id,plays_csv_json,full_innings_json,
   source_event_id,play_version,recording_generation,event_sequence)
 VALUES(tenant,bound_game,saved_play,finished_json,score_full,
   p_source_event_id,saved_version,bound_generation,source_d2);
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
   p_binding_nonce,bound_device,bound_game);
 RETURN saved_play;
END;
$export_save$;
"""
