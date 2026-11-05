-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:stats_api:read_play_export_primitives(uuid, uuid, uuid, bigint, text, text, text, bigint, uuid, text, integer)

CREATE FUNCTION stats_api.read_play_export_primitives(p_game_id uuid,p_player_id uuid,p_fact_version_id uuid,p_revision bigint,p_source_set_sha256 text,p_model_sha256 text,p_transaction_id text,p_after_d2 bigint,p_after_source_event_id uuid,p_after_metric_id text,p_page_size integer)
RETURNS TABLE(metric_id text,state text,value numeric,d2 bigint,source_event_id uuid) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $stats$
#variable_conflict use_column
DECLARE tenant uuid; receipt record;
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 IF session_user IS DISTINCT FROM 'pitchlog_app' OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'
 OR tenant IS NULL OR p_game_id IS NULL OR p_player_id IS NULL
 OR p_model_sha256 IS DISTINCT FROM 'sha256:f358df32f54bedfecb2866436e718c7bd6ece514798fe4de2325022d38a09422'
 OR pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'repeatable read'
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'on'
 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.players p WHERE p.tenant_id=tenant AND p.id=p_player_id)
 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 IF p_fact_version_id IS NULL OR p_revision IS NULL OR p_revision<1
 OR p_source_set_sha256 IS NULL OR p_source_set_sha256 !~ '^[a-f0-9]{64}$'
 OR p_transaction_id IS NULL OR p_transaction_id IS DISTINCT FROM pg_catalog.pg_current_snapshot()::text
 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 SELECT * INTO STRICT receipt FROM stats_api.open_primitive_snapshot(p_game_id,p_player_id,p_model_sha256);
 IF receipt.fact_version_id IS DISTINCT FROM p_fact_version_id OR receipt.revision IS DISTINCT FROM p_revision
 OR receipt.source_set_sha256 IS DISTINCT FROM p_source_set_sha256
 OR receipt.model_sha256 IS DISTINCT FROM p_model_sha256
 OR receipt.transaction_id IS DISTINCT FROM p_transaction_id
 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;

 IF p_page_size IS NULL OR p_page_size<1 OR p_page_size>500
 OR NOT ((p_after_d2 IS NULL AND p_after_source_event_id IS NULL AND p_after_metric_id IS NULL)
 OR (p_after_d2 IS NOT NULL AND p_after_source_event_id IS NOT NULL AND p_after_metric_id IS NOT NULL AND p_after_metric_id=ANY(ARRAY['ab','bb','catcher_interference_reached','doubles','fielding_errors','h','hbp','hits_allowed','home_runs_allowed','hr','k','pa','pitch_count','pitcher_bb','pitcher_hbp','pitcher_k','pitching_outs','rbi','runner_interference_reached','runs','runs_allowed','sf','sh','stolen_bases','total_bases','triples']::text[])))
 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 RETURN QUERY WITH requested_metrics(metric_id) AS (VALUES ('pitch_count'), ('pa'), ('ab'), ('h'), ('hr'), ('bb'), ('hbp'), ('k'), ('sh'), ('sf'), ('catcher_interference_reached'), ('runner_interference_reached'), ('doubles'), ('triples'), ('total_bases'), ('runs'), ('rbi'), ('stolen_bases'), ('pitching_outs'), ('pitcher_k'), ('pitcher_bb'), ('pitcher_hbp'), ('hits_allowed'), ('home_runs_allowed'), ('fielding_errors'), ('runs_allowed')),
canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM public.games g
 WHERE g.tenant_id=tenant AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND g.status NOT IN ('hidden','trashed')
   AND g.id=p_game_id
), canonical_raw AS (
 SELECT slot.tenant_id,slot.game_id,slot.generation AS recording_generation,
   slot.d1,e.d2,slot.confirmed_version AS slot_version,e.id AS base_event_id,
   CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END AS source_event_id,
   p.id AS play_row_id,p.version AS play_row_version,
   current_event.d5,ledger.source_fingerprint,
   current_event.payload->>'formatVersion' AS native_variant,
   current_event.payload#>>'{calculation,artifactSha256}' AS artifact_sha256,
   COUNT(*) OVER (PARTITION BY slot.tenant_id,slot.game_id,slot.generation,slot.d1) AS match_count,
   CASE WHEN gen.retired_at IS NOT NULL THEN 'excluded_retired'
     WHEN e.id IS NULL OR current_event.id IS NULL THEN 'source_unavailable'
     WHEN e.event_kind<>'play_input' THEN 'excluded_control'
     WHEN e.is_tombstone OR current_event.is_tombstone THEN 'excluded_tombstone'
     WHEN current_event.event_kind='play_delete' THEN 'excluded_delete'
     WHEN slot.d1>gen.confirmed_watermark OR slot.d1>gen.applied_prefix THEN 'source_unavailable'
     WHEN ledger.kind IS DISTINCT FROM 'accepted' OR ledger.retired_at IS NOT NULL
       OR p.id IS NULL OR p.hidden_at IS NOT NULL THEN 'source_unavailable'
     ELSE 'included' END AS preliminary_state
 FROM public.event_slots slot JOIN canonical_scope g
   ON g.tenant_id=slot.tenant_id AND g.game_id=slot.game_id
 JOIN public.recording_generations gen ON gen.tenant_id=slot.tenant_id
   AND gen.game_id=slot.game_id AND gen.generation=slot.generation
 LEFT JOIN public.operation_events e ON e.tenant_id=slot.tenant_id AND e.game_id=slot.game_id
   AND e.generation=slot.generation AND e.d1=slot.d1
   AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.ledger_kind='accepted'
 LEFT JOIN public.operation_events change ON change.tenant_id=slot.tenant_id AND change.game_id=slot.game_id
   AND change.target_generation=slot.generation AND change.target_d1=slot.d1
   AND change.expected_version=slot.confirmed_version-1 AND slot.confirmed_version>1
   AND change.ledger_kind='accepted' AND change.replaced_at IS NULL AND change.retired_at IS NULL
 LEFT JOIN public.operation_events current_event ON current_event.tenant_id=slot.tenant_id
   AND current_event.game_id=slot.game_id
   AND current_event.id=CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END
 LEFT JOIN public.idempotency_ledger ledger ON ledger.tenant_id=current_event.tenant_id
   AND ledger.d5=current_event.d5
 LEFT JOIN public.play_rows p ON p.tenant_id=current_event.tenant_id
   AND p.game_id=current_event.game_id AND p.source_event_id=current_event.id
), canonical_s AS (
 SELECT *,CASE WHEN match_count<>1 THEN 'source_unavailable'
               ELSE preliminary_state END AS source_state FROM canonical_raw
), canonical_health AS (
 SELECT g.tenant_id,g.game_id,1::bigint AS game_count,
   COUNT(*) FILTER (WHERE c.source_state='included') AS canonical_source_count,
   COUNT(*) FILTER (WHERE c.source_state='source_unavailable') AS unavailable_count,
   encode(sha256(convert_to(COALESCE(string_agg(
     jsonb_build_array(c.tenant_id,c.game_id,c.recording_generation,c.d1,c.d2,c.source_event_id,
       c.slot_version,c.play_row_id,c.play_row_version,c.source_fingerprint)::text,
     E'\n' ORDER BY c.tenant_id,c.game_id,c.d2,c.source_event_id)
     FILTER (WHERE c.source_state='included'),'accepted-play-slot-v1:empty'),'UTF8')),'hex')
     AS canonical_source_set_sha256
 FROM canonical_scope g LEFT JOIN canonical_s c
   ON c.tenant_id=g.tenant_id AND c.game_id=g.game_id
 GROUP BY g.tenant_id,g.game_id
)
, version_scope AS (
 SELECT v.* FROM sync_fence.stats_fact_versions v
 JOIN public.games g ON g.tenant_id=v.tenant_id AND g.id=v.game_id
 JOIN canonical_scope visible_game ON visible_game.tenant_id=v.tenant_id
   AND visible_game.game_id=v.game_id
 WHERE v.tenant_id=tenant AND v.model_sha256=p_model_sha256
   AND v.is_current=true AND v.invalidated_at IS NULL
   AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND v.game_id=p_game_id AND v.id=p_fact_version_id
   AND v.source_set_sha256=p_source_set_sha256 AND v.revision=p_revision
), source_members AS (
 SELECT s.* FROM sync_fence.stats_primitive_sources s
 JOIN version_scope v ON v.tenant_id=s.tenant_id AND v.game_id=s.game_id
   AND v.id=s.fact_version_id
 JOIN canonical_s c ON c.tenant_id=s.tenant_id AND c.game_id=s.game_id
   AND c.source_event_id=s.source_event_id AND c.recording_generation=s.recording_generation
   AND c.d1=s.d1 AND c.d2=s.d2 AND c.slot_version=s.slot_version
   AND c.play_row_id=s.play_row_id AND c.play_row_version=s.play_row_version
   AND c.source_fingerprint=s.source_fingerprint AND c.artifact_sha256=s.artifact_sha256
   AND c.source_state='included'
), scope_health AS (
 SELECT v.tenant_id,v.game_id,v.id,v.source_count,
   COUNT(s.source_event_id) AS actual_source_count
 FROM version_scope v LEFT JOIN source_members s ON s.tenant_id=v.tenant_id
   AND s.game_id=v.game_id AND s.fact_version_id=v.id
 GROUP BY v.tenant_id,v.game_id,v.id,v.source_count
), binding_health AS (
 SELECT h.*,
   (ch.game_id IS NULL OR h.source_count<>h.actual_source_count
    OR ch.unavailable_count>0 OR ch.canonical_source_count<>h.actual_source_count
    OR v.source_set_sha256<>ch.canonical_source_set_sha256) AS invalid
 FROM scope_health h JOIN version_scope v
   ON v.tenant_id=h.tenant_id AND v.game_id=h.game_id AND v.id=h.id
 LEFT JOIN canonical_health ch ON ch.tenant_id=h.tenant_id AND ch.game_id=h.game_id
), selected AS (
 SELECT s.tenant_id,s.game_id,CAST(p_player_id AS uuid) AS player_id,m.metric_id,
   CASE WHEN EXISTS (SELECT 1 FROM binding_health WHERE invalid)
     OR EXISTS (SELECT 1 FROM canonical_health ch LEFT JOIN version_scope bound_version
       ON bound_version.tenant_id=ch.tenant_id AND bound_version.game_id=ch.game_id
       WHERE bound_version.id IS NULL)
     OR NOT (m.metric_id=ANY(s.computed_metric_keys))
     OR COUNT(*) FILTER (WHERE f.source_event_id IS NOT NULL AND (f.state<>'available' OR f.amount IS NULL))>0
     THEN NULL ELSE COALESCE(SUM(f.amount),0) END AS amount,
   CASE WHEN EXISTS (SELECT 1 FROM binding_health WHERE invalid)
     OR EXISTS (SELECT 1 FROM canonical_health ch LEFT JOIN version_scope bound_version
       ON bound_version.tenant_id=ch.tenant_id AND bound_version.game_id=ch.game_id
       WHERE bound_version.id IS NULL)
     OR NOT (m.metric_id=ANY(s.computed_metric_keys))
     OR COUNT(*) FILTER (WHERE f.source_event_id IS NOT NULL AND (f.state<>'available' OR f.amount IS NULL))>0
     THEN 'source_unavailable' ELSE 'available' END AS state,
   s.source_event_id,s.d2
 FROM source_members s CROSS JOIN requested_metrics m
 LEFT JOIN sync_fence.stats_primitive_facts f ON f.tenant_id=s.tenant_id AND f.game_id=s.game_id
   AND f.fact_version_id=s.fact_version_id AND f.source_event_id=s.source_event_id
   AND f.metric_id=m.metric_id AND f.player_id=p_player_id
 GROUP BY s.tenant_id,s.game_id,s.fact_version_id,s.source_event_id,s.d2,
   s.computed_metric_keys,m.metric_id
)
, accumulated AS (
 SELECT *,
   CASE WHEN COUNT(*) FILTER (WHERE state<>'available' OR amount IS NULL) OVER w>0
        THEN NULL ELSE SUM(amount) OVER w END AS value,
   CASE WHEN COUNT(*) FILTER (WHERE state<>'available' OR amount IS NULL) OVER w>0
        THEN 'source_unavailable' ELSE 'available' END AS result_state
 FROM selected
 WINDOW w AS (PARTITION BY tenant_id,game_id,player_id,metric_id
   ORDER BY d2,source_event_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
)
SELECT metric_id,result_state AS state,value,d2,source_event_id FROM accumulated
WHERE (p_after_d2 IS NULL OR
 (d2,source_event_id,metric_id)>(p_after_d2,p_after_source_event_id,p_after_metric_id))
ORDER BY d2,source_event_id,metric_id LIMIT p_page_size;

END;
$stats$;

ALTER FUNCTION stats_api.read_play_export_primitives(uuid, uuid, uuid, bigint, text, text, text, bigint, uuid, text, integer) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION stats_api.read_play_export_primitives(uuid, uuid, uuid, bigint, text, text, text, bigint, uuid, text, integer) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION stats_api.read_play_export_primitives(uuid, uuid, uuid, bigint, text, text, text, bigint, uuid, text, integer) TO pitchlog_app;
