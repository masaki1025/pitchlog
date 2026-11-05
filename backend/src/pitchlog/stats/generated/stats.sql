-- 自動生成 model=sha256:60ab45878fdfc868efc15ddb0f9b84d6ab0f3583519c48a2202e3d9c3abac59d
-- 正式operation/receiptはroot binding、実DB実行前は成功を主張しない。
WITH requested_metrics(metric_id) AS (VALUES ('pitch_count'), ('pa'), ('ab'), ('h'), ('hr'), ('bb'), ('hbp'), ('k'), ('sh'), ('sf'), ('catcher_interference_reached'), ('runner_interference_reached'), ('doubles'), ('triples'), ('total_bases'), ('runs'), ('rbi'), ('stolen_bases'), ('pitching_outs'), ('pitcher_k'), ('pitcher_bb'), ('pitcher_hbp'), ('hits_allowed'), ('home_runs_allowed'), ('fielding_errors'), ('runs_allowed')),
canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM public.games g
 WHERE g.tenant_id=:tenant_id AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND g.status NOT IN ('hidden','trashed')
   AND g.status='finished' AND g.scheduled_at>=:year_start_jst AND g.scheduled_at<:year_end_jst AND (CAST(:raw_game_type_keys AS text[])=(CASE :named_category WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END)) AND g.game_type_key=ANY((CASE :named_category WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END))
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
 WHERE v.tenant_id=:tenant_id AND v.model_sha256=:model_sha256
   AND v.is_current=true AND v.invalidated_at IS NULL
   AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND v.completion_state='confirmed_ended'
   AND v.completion_receipt_id IS NOT NULL AND v.public_pointer_receipt_id IS NOT NULL
   AND g.scheduled_at>=:year_start_jst AND g.scheduled_at<:year_end_jst
   AND (CAST(:raw_game_type_keys AS text[])=(CASE :named_category WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END)) AND g.game_type_key=ANY((CASE :named_category WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END))
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
 SELECT s.tenant_id,s.game_id,CAST(:player_id AS uuid) AS player_id,m.metric_id,
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
   AND f.metric_id=m.metric_id AND f.player_id=:player_id
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
       WHERE bound_version.id IS NULL) OR NOT COALESCE((CAST(:raw_game_type_keys AS text[])=(CASE :named_category WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END)),false)
     OR EXISTS (SELECT 1 FROM version_scope coverage
                WHERE NOT (m.metric_id=ANY(coverage.computed_metric_keys)))
     OR a.complete=false THEN 'source_unavailable' ELSE 'available' END AS state,
 CASE WHEN EXISTS (SELECT 1 FROM binding_health WHERE invalid)
     OR EXISTS (SELECT 1 FROM canonical_health ch LEFT JOIN version_scope bound_version
       ON bound_version.tenant_id=ch.tenant_id AND bound_version.game_id=ch.game_id
       WHERE bound_version.id IS NULL) OR NOT COALESCE((CAST(:raw_game_type_keys AS text[])=(CASE :named_category WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END)),false)
     OR EXISTS (SELECT 1 FROM version_scope coverage
                WHERE NOT (m.metric_id=ANY(coverage.computed_metric_keys)))
     OR a.complete=false THEN NULL ELSE COALESCE(a.value,0) END AS value
FROM requested_metrics m LEFT JOIN aggregate_facts a ON a.metric_id=m.metric_id
ORDER BY m.metric_id;
