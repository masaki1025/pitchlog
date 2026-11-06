-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:stats_basic_api:read_basic_stats(uuid, text, text, text, text, text, boolean, text, integer, text)

CREATE FUNCTION stats_basic_api.read_basic_stats(p_tenant_id uuid,p_game_id text,p_year_start text,p_year_end text,p_category text,p_raw_game_type_keys text,p_official boolean,p_after_player_id text,p_page_size integer,p_model_sha256 text)
RETURNS TABLE(player_id uuid,player_name text,uniform_number text,team_record_id uuid,team_name text,metrics_json text) LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $basic$
#variable_conflict use_column
DECLARE tenant uuid; game_uuid uuid; game_count bigint; raw_keys text[]; player record; metric record; metrics jsonb; appearance_ready boolean; appearance_count bigint; query text:=$q$-- 自動生成 model=sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6
-- 正式operation/receiptはroot binding、実DB実行前は成功を主張しない。
WITH requested_metrics(metric_id) AS (VALUES ('pitch_count'), ('pa'), ('ab'), ('h'), ('hr'), ('bb'), ('hbp'), ('k'), ('sh'), ('sf'), ('catcher_interference_reached'), ('runner_interference_reached'), ('doubles'), ('triples'), ('total_bases'), ('runs'), ('rbi'), ('stolen_bases'), ('pitching_outs'), ('pitcher_k'), ('pitcher_bb'), ('batters_faced'), ('pitcher_hbp'), ('hits_allowed'), ('home_runs_allowed'), ('fielding_errors'), ('runs_allowed')),
canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM public.games g
 WHERE g.tenant_id=$1 AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND g.status NOT IN ('hidden','trashed')
   AND (($9 AND g.status='finished') OR (NOT $9 AND g.status IN ('in_progress','finished'))) AND ((($8 IS NOT NULL) AND g.id=$8) OR (($8 IS NULL) AND g.scheduled_at>=$4::timestamptz AND g.scheduled_at<$5::timestamptz)) AND (($7::text[])=(CASE $6 WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END)) AND g.game_type_key=ANY((CASE $6 WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END))
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
 LEFT JOIN sync_fence.game_lifecycle_heads h
   ON h.tenant_id=v.tenant_id AND h.game_id=v.game_id
 JOIN canonical_scope visible_game ON visible_game.tenant_id=v.tenant_id
   AND visible_game.game_id=v.game_id
 WHERE v.tenant_id=$1 AND v.model_sha256=$3
   AND v.is_current=true AND v.invalidated_at IS NULL
   AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND (($9 AND v.completion_state='confirmed_ended'
   AND v.completion_receipt_id IS NOT NULL AND v.public_pointer_receipt_id=v.completion_receipt_id
   AND h.is_finished AND h.active_stats_version_id=v.id
   AND h.active_receipt_id=v.completion_receipt_id
   AND h.active_end_event_id IS NOT NULL
   AND EXISTS (SELECT 1 FROM sync_fence.lifecycle_write_admissions a
     JOIN public.operation_events e ON e.tenant_id=a.tenant_id
       AND e.game_id=a.game_id AND e.id=a.source_event_id
     WHERE a.tenant_id=v.tenant_id AND a.game_id=v.game_id
       AND a.source_event_id=h.active_end_event_id
       AND a.receipt_id=h.active_receipt_id
       AND a.action='end' AND a.state='consumed'
       AND e.event_kind='game_end_declaration'
       AND e.ledger_kind='accepted' AND NOT e.is_tombstone
       AND e.replaced_at IS NULL AND e.retired_at IS NULL))
   OR (NOT $9 AND v.completion_state='current_open'
       AND g.status='in_progress'
       AND (h.game_id IS NULL OR (NOT h.is_finished
         AND h.active_end_event_id IS NULL
         AND h.active_receipt_id IS NULL
         AND h.active_stats_version_id IS NULL))))
   AND ((($8 IS NOT NULL) AND g.id=$8) OR (($8 IS NULL) AND g.scheduled_at>=$4::timestamptz AND g.scheduled_at<$5::timestamptz))
   AND (($7::text[])=(CASE $6 WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END)) AND g.game_type_key=ANY((CASE $6 WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END))
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
 SELECT s.tenant_id,s.game_id,CAST($2 AS uuid) AS player_id,m.metric_id,
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
   AND f.metric_id=m.metric_id AND f.player_id=$2
 GROUP BY s.tenant_id,s.game_id,s.fact_version_id,s.source_event_id,s.d2,
   s.computed_metric_keys,m.metric_id
)
, aggregate_facts AS (
 SELECT player_id, metric_id,
   CASE WHEN COUNT(*) FILTER (WHERE state<>'available' OR amount IS NULL)>0 THEN NULL
        ELSE SUM(amount) END AS value,
   BOOL_AND(state='available' AND amount IS NOT NULL) AS complete
 FROM selected GROUP BY player_id, metric_id
)
SELECT m.metric_id,
 CASE WHEN EXISTS (SELECT 1 FROM binding_health WHERE invalid)
     OR EXISTS (SELECT 1 FROM canonical_health ch LEFT JOIN version_scope bound_version
       ON bound_version.tenant_id=ch.tenant_id AND bound_version.game_id=ch.game_id
       WHERE bound_version.id IS NULL) OR NOT COALESCE((($7::text[])=(CASE $6 WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END)),false)
     OR EXISTS (SELECT 1 FROM version_scope coverage
                WHERE NOT (m.metric_id=ANY(coverage.computed_metric_keys)))
     OR a.complete=false THEN 'source_unavailable' ELSE 'available' END AS state,
 CASE WHEN EXISTS (SELECT 1 FROM binding_health WHERE invalid)
     OR EXISTS (SELECT 1 FROM canonical_health ch LEFT JOIN version_scope bound_version
       ON bound_version.tenant_id=ch.tenant_id AND bound_version.game_id=ch.game_id
       WHERE bound_version.id IS NULL) OR NOT COALESCE((($7::text[])=(CASE $6 WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END)),false)
     OR EXISTS (SELECT 1 FROM version_scope coverage
                WHERE NOT (m.metric_id=ANY(coverage.computed_metric_keys)))
     OR a.complete=false THEN NULL ELSE COALESCE(a.value,0) END AS value
FROM requested_metrics m LEFT JOIN aggregate_facts a ON a.metric_id=m.metric_id
ORDER BY m.metric_id$q$;
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 IF session_user IS DISTINCT FROM 'pitchlog_app' OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'
  OR tenant IS NULL OR p_tenant_id IS DISTINCT FROM tenant
  OR p_model_sha256 IS DISTINCT FROM 'sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6'
  OR pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'repeatable read'
  OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'on'
 THEN RAISE EXCEPTION 'basic stats boundary rejected' USING ERRCODE='42501';
 END IF;

 game_uuid:=NULLIF(p_game_id,'')::uuid;
 IF game_uuid IS NOT NULL THEN
  SELECT count(*) INTO game_count FROM public.games g
   WHERE g.tenant_id=tenant AND g.id=game_uuid
     AND g.hidden_at IS NULL AND g.trashed_at IS NULL
     AND g.status NOT IN ('hidden','trashed');
  IF game_count<>1 THEN
   RAISE EXCEPTION 'basic stats game boundary rejected' USING ERRCODE='42501';
  END IF;
  IF NOT EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions v
      JOIN public.games g ON g.tenant_id=v.tenant_id AND g.id=v.game_id
      WHERE v.tenant_id=tenant AND v.game_id=game_uuid
        AND v.model_sha256=p_model_sha256 AND v.is_current
        AND v.invalidated_at IS NULL
        AND ((p_official AND v.completion_state='confirmed_ended'
              AND v.completion_receipt_id IS NOT NULL
              AND v.public_pointer_receipt_id IS NOT NULL)
             OR (NOT p_official AND v.completion_state='current_open'))
        AND ((p_official AND g.status='finished')
             OR (NOT p_official AND g.status IN ('in_progress','finished')))) THEN
   RETURN;
  END IF;
 END IF;
 IF game_uuid IS NULL AND (NOT p_official OR p_year_start IS NULL OR
     p_year_end IS NULL OR p_year_end::timestamptz<=p_year_start::timestamptz) THEN
  RAISE EXCEPTION 'basic stats season boundary rejected' USING ERRCODE='42501';
 END IF;
 IF game_uuid IS NULL THEN
  IF NOT EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions v
      JOIN public.games g ON g.tenant_id=v.tenant_id AND g.id=v.game_id
      WHERE v.tenant_id=tenant AND v.model_sha256=p_model_sha256
        AND v.is_current AND v.invalidated_at IS NULL
        AND v.completion_state='confirmed_ended'
        AND v.completion_receipt_id IS NOT NULL
        AND v.public_pointer_receipt_id IS NOT NULL
        AND g.hidden_at IS NULL AND g.trashed_at IS NULL
        AND g.status='finished' AND g.scheduled_at>=p_year_start::timestamptz
        AND g.scheduled_at<p_year_end::timestamptz
        AND g.game_type_key=ANY(CASE p_category WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END)) THEN
   RETURN;
  END IF;
 END IF;
 IF p_official IS NULL OR p_page_size IS NULL OR p_page_size<1 OR p_page_size>200 THEN
  RAISE EXCEPTION 'basic stats page boundary rejected' USING ERRCODE='42501';
 END IF;
 IF p_after_player_id IS NOT NULL AND p_after_player_id<>'' THEN
  IF p_after_player_id !~ '^[0-9a-f]8-[0-9a-f]4-[0-9a-f]4-[0-9a-f]4-[0-9a-f]12$' THEN
   RAISE EXCEPTION 'basic stats cursor boundary rejected' USING ERRCODE='42501';
  END IF;
 END IF;
 IF p_category NOT IN ('official','practice','all') THEN
  RAISE EXCEPTION 'basic stats category boundary rejected' USING ERRCODE='42501';
 END IF;

 appearance_ready:=false;
 IF game_uuid IS NOT NULL THEN
  SELECT (
    g.import_batch_id IS NULL AND g.started_at IS NOT NULL
    AND (SELECT count(*) FROM public.game_start_attempts s
         WHERE s.tenant_id=tenant AND s.game_id=game_uuid
           AND s.outcome='committed')=1
    AND NOT EXISTS(SELECT 1 FROM public.game_start_attempts s
         WHERE s.tenant_id=tenant AND s.game_id=game_uuid
           AND s.outcome='pending')
    AND (SELECT count(*) FROM public.game_lineups l
         WHERE l.tenant_id=tenant AND l.game_id=game_uuid)=2
    AND NOT EXISTS(SELECT 1 FROM public.game_lineups l
         WHERE l.tenant_id=tenant AND l.game_id=game_uuid
           AND (l.import_batch_id IS NOT NULL OR l.team_record_id NOT IN
           (g.away_team_record_id,g.home_team_record_id)))
    AND (SELECT count(DISTINCT l.team_record_id) FROM public.game_lineups l
         WHERE l.tenant_id=tenant AND l.game_id=game_uuid)=2
    AND (SELECT count(*) FROM public.game_lineups l
         CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(
           CASE WHEN pg_catalog.jsonb_typeof(l.entries_with_uniform_number_snapshot)
             ='array' THEN l.entries_with_uniform_number_snapshot
             ELSE '[]'::jsonb END) entry(value)
         WHERE l.tenant_id=tenant AND l.game_id=game_uuid
           AND entry.value->'fielding_position'->>'kind'='fielding'
           AND entry.value->'fielding_position'->>'position'='1')=2
    AND (SELECT count(DISTINCT entry.value->>'player_id')
         FROM public.game_lineups l
         CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(
           CASE WHEN pg_catalog.jsonb_typeof(l.entries_with_uniform_number_snapshot)
             ='array' THEN l.entries_with_uniform_number_snapshot
             ELSE '[]'::jsonb END) entry(value)
         WHERE l.tenant_id=tenant AND l.game_id=game_uuid
           AND entry.value->'fielding_position'->>'kind'='fielding'
           AND entry.value->'fielding_position'->>'position'='1')=2
    AND NOT EXISTS(SELECT 1 FROM public.operation_events e
         WHERE e.tenant_id=tenant AND e.game_id=game_uuid
           AND e.event_kind NOT IN ('play_input','game_end_declaration'))
  ) INTO appearance_ready FROM public.games g
   WHERE g.tenant_id=tenant AND g.id=game_uuid;
 END IF;
 raw_keys:=string_to_array(p_raw_game_type_keys,',');
 IF raw_keys IS NULL OR pg_catalog.array_position(raw_keys,NULL) IS NOT NULL
  OR raw_keys IS DISTINCT FROM (CASE p_category WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END) THEN
RAISE EXCEPTION 'basic stats boundary rejected' USING ERRCODE='42501';
 END IF;

 FOR player IN
  SELECT p.id,p.name,p.uniform_number,p.team_record_id,tr.name AS team_name
   FROM public.players p
   JOIN public.team_records tr
     ON tr.tenant_id=p.tenant_id AND tr.id=p.team_record_id
   WHERE p.tenant_id=tenant AND p.hidden_at IS NULL
     AND tr.hidden_at IS NULL
     AND (
       (game_uuid IS NOT NULL AND p.team_record_id IN (
         SELECT g.away_team_record_id FROM public.games g
          WHERE g.tenant_id=tenant AND g.id=game_uuid
         UNION
         SELECT g.home_team_record_id FROM public.games g
          WHERE g.tenant_id=tenant AND g.id=game_uuid))
       OR
       (game_uuid IS NULL AND tr.kind='self')
     )
     AND (p_after_player_id IS NULL OR p_after_player_id='' OR
          p.id>NULLIF(p_after_player_id,'')::uuid)
   ORDER BY p.id
   LIMIT p_page_size+1
 LOOP
  metrics := '{}'::jsonb;
  FOR metric IN EXECUTE query USING tenant,player.id,p_model_sha256,
      p_year_start,p_year_end,p_category,raw_keys,game_uuid,p_official LOOP
   metrics := metrics || pg_catalog.jsonb_build_object(
     metric.metric_id,
     pg_catalog.jsonb_build_object('state',metric.state,
       'value',CASE WHEN metric.value IS NULL THEN NULL
                    ELSE metric.value::text END));
  END LOOP;
  IF appearance_ready THEN
   SELECT count(*) INTO appearance_count FROM public.game_lineups l
    CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(
      l.entries_with_uniform_number_snapshot) entry(value)
    WHERE l.tenant_id=tenant AND l.game_id=game_uuid
      AND entry.value->'fielding_position'->>'kind'='fielding'
      AND entry.value->'fielding_position'->>'position'='1'
      AND entry.value->>'player_id'=player.id::text;
   IF appearance_count>1 THEN
    RAISE EXCEPTION 'basic stats appearance source rejected' USING ERRCODE='42501';
   END IF;
   metrics:=metrics || pg_catalog.jsonb_build_object('appearances',
     pg_catalog.jsonb_build_object('state','available',
       'value',appearance_count::text));
  ELSE
   metrics:=metrics || pg_catalog.jsonb_build_object('appearances',
     pg_catalog.jsonb_build_object('state','source_unavailable','value',NULL));
  END IF;
  RETURN QUERY SELECT player.id,player.name,
    COALESCE(player.uniform_number,''),player.team_record_id,player.team_name,
    metrics::text;
 END LOOP;
END;
$basic$;

ALTER FUNCTION stats_basic_api.read_basic_stats(uuid, text, text, text, text, text, boolean, text, integer, text) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION stats_basic_api.read_basic_stats(uuid, text, text, text, text, text, boolean, text, integer, text) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION stats_basic_api.read_basic_stats(uuid, text, text, text, text, text, boolean, text, integer, text) TO pitchlog_app;
