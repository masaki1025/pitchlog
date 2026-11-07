-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:stats_basic_api:read_basic_stats(uuid, text, text, text, text, text, boolean, text, integer, text)

CREATE FUNCTION stats_basic_api.read_basic_stats(p_tenant_id uuid,p_game_id text,p_year_start text,p_year_end text,p_category text,p_raw_game_type_keys text,p_official boolean,p_after_player_id text,p_page_size integer,p_model_sha256 text)
RETURNS TABLE(player_id uuid,player_name text,uniform_number text,team_record_id uuid,team_name text,metrics_json text) LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $basic$
#variable_conflict use_column
DECLARE tenant uuid; game_uuid uuid; game_count bigint; raw_keys text[]; player record; metric record; metrics jsonb; appearance_player_ids uuid[]; appearance_metrics jsonb:='{}'::jsonb; appearance_query text:=$appearance$-- 自動生成 model=sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6
-- 正式operation/receiptはroot binding、実DB実行前は成功を主張しない。
WITH requested_metrics(metric_id) AS (VALUES ('pitch_count'), ('pa'), ('ab'), ('h'), ('hr'), ('bb'), ('hbp'), ('k'), ('sh'), ('sf'), ('catcher_interference_reached'), ('runner_interference_reached'), ('doubles'), ('triples'), ('total_bases'), ('runs'), ('rbi'), ('stolen_bases'), ('pitching_outs'), ('pitcher_k'), ('pitcher_bb'), ('batters_faced'), ('pitcher_hbp'), ('hits_allowed'), ('home_runs_allowed'), ('fielding_errors'), ('runs_allowed')),
canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM public.games g
 WHERE g.tenant_id=$1 AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND g.status NOT IN ('hidden','trashed')
   AND (($9 AND g.status='finished') OR (NOT $9 AND g.status IN ('in_progress','finished'))) AND ((($8 IS NOT NULL) AND g.id=$8) OR (($8 IS NULL) AND g.scheduled_at>=$4::timestamptz AND g.scheduled_at<$5::timestamptz)) AND (($7::text[])=(CASE $6 WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END)) AND g.game_type_key=ANY((CASE $6 WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END))
), canonical_undos AS (
 SELECT n.* FROM sync_fence.nonplay_write_admissions n
 JOIN canonical_scope scope ON (scope.tenant_id,scope.game_id)=(n.tenant_id,n.game_id)
 JOIN sync_fence.writer_bindings ub ON n.tenant_id IS NOT DISTINCT FROM ub.tenant_id AND n.attempt_id IS NOT DISTINCT FROM ub.attempt_id AND n.phase_id IS NOT DISTINCT FROM ub.phase_id AND n.authority_id IS NOT DISTINCT FROM ub.authority_id AND n.control_instance IS NOT DISTINCT FROM ub.control_instance AND n.business_instance IS NOT DISTINCT FROM ub.business_instance AND n.restore_epoch IS NOT DISTINCT FROM ub.restore_epoch AND n.control_version IS NOT DISTINCT FROM ub.control_version AND n.issuer IS NOT DISTINCT FROM ub.issuer AND n.lease_id IS NOT DISTINCT FROM ub.lease_id AND n.device_id IS NOT DISTINCT FROM ub.device_id AND n.game_id IS NOT DISTINCT FROM ub.game_id AND n.wire_d4 IS NOT DISTINCT FROM ub.wire_d4 AND n.internal_generation IS NOT DISTINCT FROM ub.internal_generation AND n.recovery_generation IS NOT DISTINCT FROM ub.recovery_generation AND n.codec_version IS NOT DISTINCT FROM ub.codec_version AND n.request_fingerprint IS NOT DISTINCT FROM ub.request_fingerprint AND n.d5 IS NOT DISTINCT FROM ub.d5 AND n.event_fingerprint IS NOT DISTINCT FROM ub.event_fingerprint AND n.system_identifier IS NOT DISTINCT FROM ub.system_identifier AND n.database_oid IS NOT DISTINCT FROM ub.database_oid AND n.postmaster_started_at IS NOT DISTINCT FROM ub.postmaster_started_at AND n.backend_pid IS NOT DISTINCT FROM ub.backend_pid AND n.backend_start IS NOT DISTINCT FROM ub.backend_start AND n.transaction_id IS NOT DISTINCT FROM ub.transaction_id AND n.nonce_digest IS NOT DISTINCT FROM ub.nonce_digest AND n.expires_at IS NOT DISTINCT FROM ub.expires_at
 JOIN public.operation_events u ON (u.tenant_id,u.game_id,u.id)=(n.tenant_id,n.game_id,n.source_event_id)
 JOIN public.idempotency_ledger ul ON ul.tenant_id=u.tenant_id AND ul.d5=u.d5
 JOIN public.event_slots us ON (us.tenant_id,us.game_id,us.generation,us.d1)
  =(u.tenant_id,u.game_id,u.generation,u.d1) AND us.confirmed_version=1
 JOIN public.operation_events t ON (t.tenant_id,t.game_id,t.id)=(n.tenant_id,n.game_id,n.target_event_id)
 JOIN public.idempotency_ledger tl ON tl.tenant_id=t.tenant_id AND tl.d5=t.d5
 JOIN public.play_rows tp ON (tp.tenant_id,tp.game_id,tp.id)=(n.tenant_id,n.game_id,n.target_play_id)
  AND tp.source_event_id=t.id AND tp.hidden_at IS NOT NULL
 WHERE n.state='consumed' AND n.consumed_at IS NOT NULL
 AND n.preparation_json::jsonb=n.preparation
 AND n.frame_id=(n.preparation->>'frame_id')::uuid
 AND n.frame_digest=n.preparation->>'frame_digest'
 AND n.artifact_sha256=n.preparation->>'artifact_sha256'
 AND n.source_event_id=(n.preparation->>'event_id')::uuid
 AND n.target_event_id=(n.preparation->'target'->'source'->>'eventId')::uuid
 AND n.target_play_id=(n.preparation->'target'->>'playId')::uuid
 AND n.checkpoint_id=(n.preparation->'before_source'->'checkpoint'->'ref'->>'id')::uuid
 AND n.checkpoint_revision=(n.preparation->'before_source'->'checkpoint'->'ref'->>'revision')::bigint
 AND n.checkpoint_digest=n.preparation->'storage'->'row'->>'content_digest'
 AND u.event_kind='undo' AND u.ledger_kind='accepted' AND ul.kind='accepted'
 AND u.d5=n.d5 AND u.generation=n.internal_generation AND u.d1=n.source_d1
 AND u.d2 IS NULL AND u.state_diff IS NULL AND NOT u.is_tombstone
 AND u.replaced_at IS NULL AND u.retired_at IS NULL AND u.import_batch_id IS NULL
 AND NOT u.migration_unverified AND ul.retired_at IS NULL AND ul.import_batch_id IS NULL
 AND ul.source_fingerprint=n.event_fingerprint
 AND u.payload=n.preparation->'event_original'->'payload'
 AND u.payload->'calculation'->'response'=n.preparation->'response'
 AND u.payload->>'artifactSha256'=n.artifact_sha256
 AND u.target_generation=n.target_generation AND u.target_d1=n.target_d1
 AND t.event_kind='play_input' AND t.ledger_kind='accepted' AND tl.kind='accepted'
 AND t.generation=n.target_generation AND t.d1=n.target_d1
 AND t.replaced_at IS NULL AND t.retired_at IS NULL AND t.import_batch_id IS NULL
 AND NOT t.is_tombstone AND NOT t.migration_unverified
 AND tl.retired_at IS NULL AND tl.import_batch_id IS NULL
 AND tl.source_fingerprint=n.preparation->'target'->'source'->>'fingerprint'
 AND tp.import_batch_id IS NULL AND NOT tp.migration_unverified
), canonical_raw AS (
 SELECT slot.tenant_id,slot.game_id,slot.generation AS recording_generation,
   slot.d1,e.d2,slot.confirmed_version AS slot_version,e.id AS base_event_id,
   CASE WHEN p3h.capsule_id IS NOT NULL AND slot.d1<=p3c.watermark THEN p3i.effective_event_id ELSE CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END END AS source_event_id,
   p.id AS play_row_id,p.version AS play_row_version,
   current_event.d5,ledger.source_fingerprint,
   CASE WHEN p3h.capsule_id IS NOT NULL AND slot.d1<=p3c.watermark THEN p3i.payload->>'formatVersion' ELSE current_event.payload->>'formatVersion' END AS native_variant,
   CASE WHEN p3h.capsule_id IS NOT NULL AND slot.d1<=p3c.watermark THEN p3i.payload#>>'{calculation,artifactSha256}' ELSE current_event.payload#>>'{calculation,artifactSha256}' END AS artifact_sha256,
   COUNT(*) OVER (PARTITION BY slot.tenant_id,slot.game_id,slot.generation,slot.d1) AS match_count,
   CASE WHEN gen.retired_at IS NOT NULL THEN 'excluded_retired'
     WHEN e.id IS NULL OR current_event.id IS NULL THEN 'source_unavailable'
     WHEN p3h.capsule_id IS NOT NULL AND (
       p3c.id IS NULL OR p3c.source_set_digest IS DISTINCT FROM p3h.source_set_digest
       OR p3c.stats_version_id IS DISTINCT FROM p3h.stats_version_id
       OR (slot.d1<=p3c.watermark AND (
       p3i.d1 IS NULL OR p3i.original_event_id IS DISTINCT FROM e.id
       OR p3i.effective_event_id IS DISTINCT FROM
         (CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END)
       OR p3i.effective_play_row_id IS DISTINCT FROM p.id
       OR p3i.original_payload IS DISTINCT FROM e.payload
       OR p3i.play_row IS DISTINCT FROM pg_catalog.to_jsonb(p)
       OR p3i.payload->>'formatVersion' IS DISTINCT FROM 'play-prefix-play-v3'))
     ) THEN 'source_unavailable'
     WHEN e.event_kind='undo' AND NOT EXISTS (SELECT 1 FROM canonical_undos verified WHERE verified.source_event_id=current_event.id) THEN 'source_unavailable'
     WHEN e.event_kind<>'play_input' THEN 'excluded_control'
     WHEN e.is_tombstone OR current_event.is_tombstone THEN 'excluded_tombstone'
     WHEN current_event.event_kind='play_delete' THEN 'excluded_delete'
     WHEN slot.d1>gen.confirmed_watermark OR slot.d1>gen.applied_prefix THEN 'source_unavailable'
     WHEN undo.source_event_id IS NOT NULL AND undo.source_event_id IS DISTINCT FROM NULL::uuid /* restore-undo-event */ THEN 'excluded_undo'
     WHEN ledger.kind IS DISTINCT FROM 'accepted' OR ledger.retired_at IS NOT NULL
       OR p.id IS NULL OR (p.hidden_at IS NOT NULL AND NOT COALESCE(undo.source_event_id=NULL::uuid /* restore-undo-event */,false)) THEN 'source_unavailable'
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
 LEFT JOIN sync_fence.p3_projection_heads p3h
   ON (p3h.tenant_id,p3h.game_id,p3h.internal_generation)
   =(slot.tenant_id,slot.game_id,slot.generation)
 LEFT JOIN sync_fence.p3_projection_capsules p3c
   ON (p3c.tenant_id,p3c.game_id,p3c.internal_generation,p3c.id)
   =(p3h.tenant_id,p3h.game_id,p3h.internal_generation,p3h.capsule_id)
 LEFT JOIN sync_fence.p3_projection_capsule_items p3i
   ON (p3i.tenant_id,p3i.game_id,p3i.internal_generation,p3i.capsule_id,p3i.d1)
   =(p3h.tenant_id,p3h.game_id,p3h.internal_generation,p3h.capsule_id,slot.d1)
 LEFT JOIN public.operation_events current_event ON current_event.tenant_id=slot.tenant_id
   AND current_event.game_id=slot.game_id
   AND current_event.id=CASE WHEN p3h.capsule_id IS NOT NULL AND slot.d1<=p3c.watermark THEN p3i.effective_event_id ELSE CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END END
 LEFT JOIN public.idempotency_ledger ledger ON ledger.tenant_id=current_event.tenant_id
   AND ledger.d5=current_event.d5
 LEFT JOIN public.play_rows p ON p.tenant_id=current_event.tenant_id
   AND p.game_id=current_event.game_id AND p.source_event_id=current_event.id
 LEFT JOIN canonical_undos undo ON undo.tenant_id=current_event.tenant_id
   AND undo.game_id=current_event.game_id AND undo.target_event_id=current_event.id
   AND undo.target_play_id=p.id
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
),
appearance_games AS MATERIALIZED (SELECT DISTINCT game_id FROM version_scope),
appearance_packets AS MATERIALIZED (
 SELECT g.game_id,s.record_json::jsonb AS packet FROM appearance_games g
 CROSS JOIN LATERAL stats_api.read_pitcher_appearance_source($1,g.game_id,$9) s
), appearance_scope AS MATERIALIZED (
 SELECT s.* FROM appearance_packets packet CROSS JOIN LATERAL
 pg_catalog.jsonb_to_record(packet.packet->'scope')
 AS s(tenant_id uuid,game_id uuid,fact_version_id uuid,revision bigint,source_set_sha256 text,checkpoint_id uuid,checkpoint_generation bigint,checkpoint_revision bigint,checkpoint_digest text,d3 bigint,lifecycle_receipt_id uuid,entry_set_sha256 text,supply_complete boolean,member_count bigint)
 WHERE packet.packet->'scope'<>'null'::jsonb
), appearance_members AS MATERIALIZED (
 SELECT m.* FROM appearance_packets packet CROSS JOIN LATERAL
 pg_catalog.jsonb_to_recordset(packet.packet->'members') AS m(
 tenant_id uuid,game_id uuid,fact_version_id uuid,revision bigint,source_set_sha256 text,checkpoint_id uuid,checkpoint_generation bigint,checkpoint_revision bigint,checkpoint_digest text,d3 bigint,lifecycle_receipt_id uuid,entry_set_sha256 text,player_id uuid,proof_kind text,proof_source_id text)
)
SELECT requested.player_id,metric.metric_id,metric.state,metric.value
FROM pg_catalog.unnest($10::uuid[]) requested(player_id)
CROSS JOIN LATERAL (-- 生成元: backend/domain/stats-appearance.model.json。真正scope/member CTEの供給前は製品提供不可。
SELECT 'appearances' AS metric_id,
 CASE WHEN invalid_supply THEN 'source_unavailable' ELSE 'available' END AS state,
 CASE WHEN invalid_supply THEN NULL ELSE (
   SELECT COUNT(DISTINCT m.game_id) FROM appearance_members m
   JOIN appearance_scope s ON m.tenant_id=s.tenant_id AND m.game_id=s.game_id AND m.fact_version_id=s.fact_version_id AND m.revision=s.revision AND m.source_set_sha256=s.source_set_sha256 AND m.checkpoint_id=s.checkpoint_id AND m.checkpoint_generation=s.checkpoint_generation AND m.checkpoint_revision=s.checkpoint_revision AND m.checkpoint_digest=s.checkpoint_digest AND m.d3=s.d3 AND m.lifecycle_receipt_id IS NOT DISTINCT FROM s.lifecycle_receipt_id AND m.entry_set_sha256=s.entry_set_sha256
   WHERE m.tenant_id=$1 AND m.player_id=requested.player_id
 ) END AS value
FROM (SELECT
 (SELECT count(*) FROM appearance_games) IS NULL OR (SELECT count(*) FROM appearance_games)<0
 OR (SELECT COUNT(*) FROM appearance_scope s WHERE s.tenant_id=$1)
    <>(SELECT count(*) FROM appearance_games)
 OR EXISTS(SELECT 1 FROM appearance_scope s WHERE s.tenant_id=$1
   AND (s.supply_complete IS NOT TRUE OR s.tenant_id IS NULL OR s.game_id IS NULL OR s.fact_version_id IS NULL OR s.revision IS NULL OR s.source_set_sha256 IS NULL OR s.checkpoint_id IS NULL OR s.checkpoint_generation IS NULL OR s.checkpoint_revision IS NULL OR s.checkpoint_digest IS NULL OR s.d3 IS NULL OR s.entry_set_sha256 IS NULL
     OR s.revision<=0 OR s.member_count IS NULL OR s.member_count<0
     OR s.member_count<>(SELECT COUNT(*) FROM appearance_members m WHERE m.tenant_id=s.tenant_id AND m.game_id=s.game_id AND m.fact_version_id=s.fact_version_id AND m.revision=s.revision AND m.source_set_sha256=s.source_set_sha256 AND m.checkpoint_id=s.checkpoint_id AND m.checkpoint_generation=s.checkpoint_generation AND m.checkpoint_revision=s.checkpoint_revision AND m.checkpoint_digest=s.checkpoint_digest AND m.d3=s.d3 AND m.lifecycle_receipt_id IS NOT DISTINCT FROM s.lifecycle_receipt_id AND m.entry_set_sha256=s.entry_set_sha256)))
 OR EXISTS(SELECT 1 FROM appearance_scope s WHERE s.tenant_id=$1
   GROUP BY s.tenant_id,s.game_id HAVING COUNT(*)<>1)
 OR EXISTS(SELECT 1 FROM appearance_members m WHERE m.tenant_id=$1
   AND (m.proof_kind NOT IN ('defensive-half-entry','pitcher-defensive-entry') OR m.proof_kind IS NULL
     OR m.player_id IS NULL OR m.proof_source_id IS NULL
     OR NOT EXISTS(SELECT 1 FROM appearance_scope s WHERE m.tenant_id=s.tenant_id AND m.game_id=s.game_id AND m.fact_version_id=s.fact_version_id AND m.revision=s.revision AND m.source_set_sha256=s.source_set_sha256 AND m.checkpoint_id=s.checkpoint_id AND m.checkpoint_generation=s.checkpoint_generation AND m.checkpoint_revision=s.checkpoint_revision AND m.checkpoint_digest=s.checkpoint_digest AND m.d3=s.d3 AND m.lifecycle_receipt_id IS NOT DISTINCT FROM s.lifecycle_receipt_id AND m.entry_set_sha256=s.entry_set_sha256)))
 AS invalid_supply) supply
) metric
$appearance$;
query text:=$q$-- 自動生成 model=sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6
-- 正式operation/receiptはroot binding、実DB実行前は成功を主張しない。
WITH requested_metrics(metric_id) AS (VALUES ('pitch_count'), ('pa'), ('ab'), ('h'), ('hr'), ('bb'), ('hbp'), ('k'), ('sh'), ('sf'), ('catcher_interference_reached'), ('runner_interference_reached'), ('doubles'), ('triples'), ('total_bases'), ('runs'), ('rbi'), ('stolen_bases'), ('pitching_outs'), ('pitcher_k'), ('pitcher_bb'), ('batters_faced'), ('pitcher_hbp'), ('hits_allowed'), ('home_runs_allowed'), ('fielding_errors'), ('runs_allowed')),
canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM public.games g
 WHERE g.tenant_id=$1 AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND g.status NOT IN ('hidden','trashed')
   AND (($9 AND g.status='finished') OR (NOT $9 AND g.status IN ('in_progress','finished'))) AND ((($8 IS NOT NULL) AND g.id=$8) OR (($8 IS NULL) AND g.scheduled_at>=$4::timestamptz AND g.scheduled_at<$5::timestamptz)) AND (($7::text[])=(CASE $6 WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END)) AND g.game_type_key=ANY((CASE $6 WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END))
), canonical_undos AS (
 SELECT n.* FROM sync_fence.nonplay_write_admissions n
 JOIN canonical_scope scope ON (scope.tenant_id,scope.game_id)=(n.tenant_id,n.game_id)
 JOIN sync_fence.writer_bindings ub ON n.tenant_id IS NOT DISTINCT FROM ub.tenant_id AND n.attempt_id IS NOT DISTINCT FROM ub.attempt_id AND n.phase_id IS NOT DISTINCT FROM ub.phase_id AND n.authority_id IS NOT DISTINCT FROM ub.authority_id AND n.control_instance IS NOT DISTINCT FROM ub.control_instance AND n.business_instance IS NOT DISTINCT FROM ub.business_instance AND n.restore_epoch IS NOT DISTINCT FROM ub.restore_epoch AND n.control_version IS NOT DISTINCT FROM ub.control_version AND n.issuer IS NOT DISTINCT FROM ub.issuer AND n.lease_id IS NOT DISTINCT FROM ub.lease_id AND n.device_id IS NOT DISTINCT FROM ub.device_id AND n.game_id IS NOT DISTINCT FROM ub.game_id AND n.wire_d4 IS NOT DISTINCT FROM ub.wire_d4 AND n.internal_generation IS NOT DISTINCT FROM ub.internal_generation AND n.recovery_generation IS NOT DISTINCT FROM ub.recovery_generation AND n.codec_version IS NOT DISTINCT FROM ub.codec_version AND n.request_fingerprint IS NOT DISTINCT FROM ub.request_fingerprint AND n.d5 IS NOT DISTINCT FROM ub.d5 AND n.event_fingerprint IS NOT DISTINCT FROM ub.event_fingerprint AND n.system_identifier IS NOT DISTINCT FROM ub.system_identifier AND n.database_oid IS NOT DISTINCT FROM ub.database_oid AND n.postmaster_started_at IS NOT DISTINCT FROM ub.postmaster_started_at AND n.backend_pid IS NOT DISTINCT FROM ub.backend_pid AND n.backend_start IS NOT DISTINCT FROM ub.backend_start AND n.transaction_id IS NOT DISTINCT FROM ub.transaction_id AND n.nonce_digest IS NOT DISTINCT FROM ub.nonce_digest AND n.expires_at IS NOT DISTINCT FROM ub.expires_at
 JOIN public.operation_events u ON (u.tenant_id,u.game_id,u.id)=(n.tenant_id,n.game_id,n.source_event_id)
 JOIN public.idempotency_ledger ul ON ul.tenant_id=u.tenant_id AND ul.d5=u.d5
 JOIN public.event_slots us ON (us.tenant_id,us.game_id,us.generation,us.d1)
  =(u.tenant_id,u.game_id,u.generation,u.d1) AND us.confirmed_version=1
 JOIN public.operation_events t ON (t.tenant_id,t.game_id,t.id)=(n.tenant_id,n.game_id,n.target_event_id)
 JOIN public.idempotency_ledger tl ON tl.tenant_id=t.tenant_id AND tl.d5=t.d5
 JOIN public.play_rows tp ON (tp.tenant_id,tp.game_id,tp.id)=(n.tenant_id,n.game_id,n.target_play_id)
  AND tp.source_event_id=t.id AND tp.hidden_at IS NOT NULL
 WHERE n.state='consumed' AND n.consumed_at IS NOT NULL
 AND n.preparation_json::jsonb=n.preparation
 AND n.frame_id=(n.preparation->>'frame_id')::uuid
 AND n.frame_digest=n.preparation->>'frame_digest'
 AND n.artifact_sha256=n.preparation->>'artifact_sha256'
 AND n.source_event_id=(n.preparation->>'event_id')::uuid
 AND n.target_event_id=(n.preparation->'target'->'source'->>'eventId')::uuid
 AND n.target_play_id=(n.preparation->'target'->>'playId')::uuid
 AND n.checkpoint_id=(n.preparation->'before_source'->'checkpoint'->'ref'->>'id')::uuid
 AND n.checkpoint_revision=(n.preparation->'before_source'->'checkpoint'->'ref'->>'revision')::bigint
 AND n.checkpoint_digest=n.preparation->'storage'->'row'->>'content_digest'
 AND u.event_kind='undo' AND u.ledger_kind='accepted' AND ul.kind='accepted'
 AND u.d5=n.d5 AND u.generation=n.internal_generation AND u.d1=n.source_d1
 AND u.d2 IS NULL AND u.state_diff IS NULL AND NOT u.is_tombstone
 AND u.replaced_at IS NULL AND u.retired_at IS NULL AND u.import_batch_id IS NULL
 AND NOT u.migration_unverified AND ul.retired_at IS NULL AND ul.import_batch_id IS NULL
 AND ul.source_fingerprint=n.event_fingerprint
 AND u.payload=n.preparation->'event_original'->'payload'
 AND u.payload->'calculation'->'response'=n.preparation->'response'
 AND u.payload->>'artifactSha256'=n.artifact_sha256
 AND u.target_generation=n.target_generation AND u.target_d1=n.target_d1
 AND t.event_kind='play_input' AND t.ledger_kind='accepted' AND tl.kind='accepted'
 AND t.generation=n.target_generation AND t.d1=n.target_d1
 AND t.replaced_at IS NULL AND t.retired_at IS NULL AND t.import_batch_id IS NULL
 AND NOT t.is_tombstone AND NOT t.migration_unverified
 AND tl.retired_at IS NULL AND tl.import_batch_id IS NULL
 AND tl.source_fingerprint=n.preparation->'target'->'source'->>'fingerprint'
 AND tp.import_batch_id IS NULL AND NOT tp.migration_unverified
), canonical_raw AS (
 SELECT slot.tenant_id,slot.game_id,slot.generation AS recording_generation,
   slot.d1,e.d2,slot.confirmed_version AS slot_version,e.id AS base_event_id,
   CASE WHEN p3h.capsule_id IS NOT NULL AND slot.d1<=p3c.watermark THEN p3i.effective_event_id ELSE CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END END AS source_event_id,
   p.id AS play_row_id,p.version AS play_row_version,
   current_event.d5,ledger.source_fingerprint,
   CASE WHEN p3h.capsule_id IS NOT NULL AND slot.d1<=p3c.watermark THEN p3i.payload->>'formatVersion' ELSE current_event.payload->>'formatVersion' END AS native_variant,
   CASE WHEN p3h.capsule_id IS NOT NULL AND slot.d1<=p3c.watermark THEN p3i.payload#>>'{calculation,artifactSha256}' ELSE current_event.payload#>>'{calculation,artifactSha256}' END AS artifact_sha256,
   COUNT(*) OVER (PARTITION BY slot.tenant_id,slot.game_id,slot.generation,slot.d1) AS match_count,
   CASE WHEN gen.retired_at IS NOT NULL THEN 'excluded_retired'
     WHEN e.id IS NULL OR current_event.id IS NULL THEN 'source_unavailable'
     WHEN p3h.capsule_id IS NOT NULL AND (
       p3c.id IS NULL OR p3c.source_set_digest IS DISTINCT FROM p3h.source_set_digest
       OR p3c.stats_version_id IS DISTINCT FROM p3h.stats_version_id
       OR (slot.d1<=p3c.watermark AND (
       p3i.d1 IS NULL OR p3i.original_event_id IS DISTINCT FROM e.id
       OR p3i.effective_event_id IS DISTINCT FROM
         (CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END)
       OR p3i.effective_play_row_id IS DISTINCT FROM p.id
       OR p3i.original_payload IS DISTINCT FROM e.payload
       OR p3i.play_row IS DISTINCT FROM pg_catalog.to_jsonb(p)
       OR p3i.payload->>'formatVersion' IS DISTINCT FROM 'play-prefix-play-v3'))
     ) THEN 'source_unavailable'
     WHEN e.event_kind='undo' AND NOT EXISTS (SELECT 1 FROM canonical_undos verified WHERE verified.source_event_id=current_event.id) THEN 'source_unavailable'
     WHEN e.event_kind<>'play_input' THEN 'excluded_control'
     WHEN e.is_tombstone OR current_event.is_tombstone THEN 'excluded_tombstone'
     WHEN current_event.event_kind='play_delete' THEN 'excluded_delete'
     WHEN slot.d1>gen.confirmed_watermark OR slot.d1>gen.applied_prefix THEN 'source_unavailable'
     WHEN undo.source_event_id IS NOT NULL AND undo.source_event_id IS DISTINCT FROM NULL::uuid /* restore-undo-event */ THEN 'excluded_undo'
     WHEN ledger.kind IS DISTINCT FROM 'accepted' OR ledger.retired_at IS NOT NULL
       OR p.id IS NULL OR (p.hidden_at IS NOT NULL AND NOT COALESCE(undo.source_event_id=NULL::uuid /* restore-undo-event */,false)) THEN 'source_unavailable'
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
 LEFT JOIN sync_fence.p3_projection_heads p3h
   ON (p3h.tenant_id,p3h.game_id,p3h.internal_generation)
   =(slot.tenant_id,slot.game_id,slot.generation)
 LEFT JOIN sync_fence.p3_projection_capsules p3c
   ON (p3c.tenant_id,p3c.game_id,p3c.internal_generation,p3c.id)
   =(p3h.tenant_id,p3h.game_id,p3h.internal_generation,p3h.capsule_id)
 LEFT JOIN sync_fence.p3_projection_capsule_items p3i
   ON (p3i.tenant_id,p3i.game_id,p3i.internal_generation,p3i.capsule_id,p3i.d1)
   =(p3h.tenant_id,p3h.game_id,p3h.internal_generation,p3h.capsule_id,slot.d1)
 LEFT JOIN public.operation_events current_event ON current_event.tenant_id=slot.tenant_id
   AND current_event.game_id=slot.game_id
   AND current_event.id=CASE WHEN p3h.capsule_id IS NOT NULL AND slot.d1<=p3c.watermark THEN p3i.effective_event_id ELSE CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END END
 LEFT JOIN public.idempotency_ledger ledger ON ledger.tenant_id=current_event.tenant_id
   AND ledger.d5=current_event.d5
 LEFT JOIN public.play_rows p ON p.tenant_id=current_event.tenant_id
   AND p.game_id=current_event.game_id AND p.source_event_id=current_event.id
 LEFT JOIN canonical_undos undo ON undo.tenant_id=current_event.tenant_id
   AND undo.game_id=current_event.game_id AND undo.target_event_id=current_event.id
   AND undo.target_play_id=p.id
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
 raw_keys:=string_to_array(p_raw_game_type_keys,',');
 IF raw_keys IS NULL OR pg_catalog.array_position(raw_keys,NULL) IS NOT NULL
  OR raw_keys IS DISTINCT FROM (CASE p_category WHEN 'official' THEN ARRAY['game_official','game_semi_official']::text[] WHEN 'practice' THEN ARRAY['game_open','game_intrasquad','game_other']::text[] WHEN 'all' THEN ARRAY['game_official','game_semi_official','game_open','game_intrasquad','game_other']::text[] ELSE NULL::text[] END) THEN
RAISE EXCEPTION 'basic stats boundary rejected' USING ERRCODE='42501';
 END IF;
 SELECT pg_catalog.array_agg(page.id ORDER BY page.id) INTO appearance_player_ids FROM (  SELECT p.id,p.name,p.uniform_number,p.team_record_id,tr.name AS team_name
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
) page;
 FOR metric IN EXECUTE appearance_query USING tenant,NULL::uuid,p_model_sha256,p_year_start,p_year_end,p_category,raw_keys,game_uuid,p_official,appearance_player_ids LOOP
  appearance_metrics:=appearance_metrics || pg_catalog.jsonb_build_object(metric.player_id::text,pg_catalog.jsonb_build_object('state',metric.state,'value',CASE WHEN metric.value IS NULL THEN NULL ELSE metric.value::text END));
 END LOOP;

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
  metrics:=metrics || pg_catalog.jsonb_build_object('appearances',
    COALESCE(appearance_metrics->player.id::text,
    pg_catalog.jsonb_build_object('state','source_unavailable','value',NULL)));
  RETURN QUERY SELECT player.id,player.name,
    COALESCE(player.uniform_number,''),player.team_record_id,player.team_name,
    metrics::text;
 END LOOP;
END;
$basic$;

ALTER FUNCTION stats_basic_api.read_basic_stats(uuid, text, text, text, text, text, boolean, text, integer, text) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION stats_basic_api.read_basic_stats(uuid, text, text, text, text, text, boolean, text, integer, text) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION stats_basic_api.read_basic_stats(uuid, text, text, text, text, text, boolean, text, integer, text) TO pitchlog_app;
