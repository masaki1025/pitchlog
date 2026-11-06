-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:stats_api:open_primitive_snapshot(uuid, uuid, text)

CREATE FUNCTION stats_api.open_primitive_snapshot(p_game_id uuid,p_player_id uuid,p_model_sha256 text)
RETURNS TABLE(fact_version_id uuid,revision bigint,source_set_sha256 text,model_sha256 text,source_count bigint,row_count bigint,transaction_id text,completion_state text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $stats$
#variable_conflict use_column
DECLARE tenant uuid; p_fact_version_id uuid; p_revision bigint; p_source_set_sha256 text; audit record; health record;
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 IF session_user IS DISTINCT FROM 'pitchlog_app' OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'
 OR tenant IS NULL OR p_game_id IS NULL OR p_player_id IS NULL
 OR p_model_sha256 IS DISTINCT FROM 'sha256:60ab45878fdfc868efc15ddb0f9b84d6ab0f3583519c48a2202e3d9c3abac59d'
 OR pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'repeatable read'
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'on'
 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.players p WHERE p.tenant_id=tenant AND p.id=p_player_id)
 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;

 SELECT v.id,v.revision,v.source_set_sha256 INTO STRICT p_fact_version_id,p_revision,p_source_set_sha256
 FROM sync_fence.stats_fact_versions v WHERE v.tenant_id=tenant AND v.game_id=p_game_id
 AND v.model_sha256=p_model_sha256 AND v.is_current AND v.invalidated_at IS NULL
 AND v.rule_sha256 ~ '^[a-f0-9]{64}$'
 AND v.t5_artifact_set_sha256='28af30fd1b1300c805b7dcb243fc7b32ab9d6db9fc10c38bdcbc63fa85c3a0de' AND v.completion_state='current_open';
 SELECT * INTO STRICT health FROM (WITH canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM public.games g
 WHERE g.tenant_id=tenant AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND g.status NOT IN ('hidden','trashed')
   AND g.id=p_game_id
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
   CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END AS source_event_id,
   p.id AS play_row_id,p.version AS play_row_version,
   current_event.d5,ledger.source_fingerprint,
   current_event.payload->>'formatVersion' AS native_variant,
   current_event.payload#>>'{calculation,artifactSha256}' AS artifact_sha256,
   COUNT(*) OVER (PARTITION BY slot.tenant_id,slot.game_id,slot.generation,slot.d1) AS match_count,
   CASE WHEN gen.retired_at IS NOT NULL THEN 'excluded_retired'
     WHEN e.id IS NULL OR current_event.id IS NULL THEN 'source_unavailable'
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
 LEFT JOIN public.operation_events current_event ON current_event.tenant_id=slot.tenant_id
   AND current_event.game_id=slot.game_id
   AND current_event.id=CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END
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
SELECT COALESCE(ch.game_count,0) AS game_count,COALESCE(ch.canonical_source_count,0) AS canonical_source_count,COALESCE(ch.unavailable_count,0) AS unavailable_count,COALESCE(ch.canonical_source_set_sha256,encode(sha256(convert_to('accepted-play-slot-v1:empty','UTF8')),'hex')) AS canonical_source_set_sha256 FROM (VALUES(1)) singleton(n) LEFT JOIN canonical_health ch ON true) canonical_result;
 IF health.game_count IS DISTINCT FROM 1::bigint THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 SELECT * INTO STRICT audit FROM (WITH requested_metrics(metric_id) AS (VALUES ('pitch_count'), ('pa'), ('ab'), ('h'), ('hr'), ('bb'), ('hbp'), ('k'), ('sh'), ('sf'), ('catcher_interference_reached'), ('runner_interference_reached'), ('doubles'), ('triples'), ('total_bases'), ('runs'), ('rbi'), ('stolen_bases'), ('pitching_outs'), ('pitcher_k'), ('pitcher_bb'), ('pitcher_hbp'), ('hits_allowed'), ('home_runs_allowed'), ('fielding_errors'), ('runs_allowed')),
canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM public.games g
 WHERE g.tenant_id=tenant AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND g.status NOT IN ('hidden','trashed')
   AND g.id=p_game_id
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
   CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END AS source_event_id,
   p.id AS play_row_id,p.version AS play_row_version,
   current_event.d5,ledger.source_fingerprint,
   current_event.payload->>'formatVersion' AS native_variant,
   current_event.payload#>>'{calculation,artifactSha256}' AS artifact_sha256,
   COUNT(*) OVER (PARTITION BY slot.tenant_id,slot.game_id,slot.generation,slot.d1) AS match_count,
   CASE WHEN gen.retired_at IS NOT NULL THEN 'excluded_retired'
     WHEN e.id IS NULL OR current_event.id IS NULL THEN 'source_unavailable'
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
 LEFT JOIN public.operation_events current_event ON current_event.tenant_id=slot.tenant_id
   AND current_event.game_id=slot.game_id
   AND current_event.id=CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END
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
SELECT v.id AS fact_version_id,v.revision,v.source_set_sha256,v.model_sha256,
 v.source_count,(SELECT COUNT(*) FROM selected) AS row_count,
 pg_current_snapshot()::text AS transaction_id,v.completion_state,
 h.actual_source_count,ch.canonical_source_count,ch.unavailable_count,
 ch.canonical_source_set_sha256
FROM version_scope v JOIN scope_health h
 ON h.tenant_id=v.tenant_id AND h.game_id=v.game_id AND h.id=v.id
JOIN canonical_health ch ON ch.tenant_id=v.tenant_id AND ch.game_id=v.game_id) snapshot_result;
  IF audit.fact_version_id IS NULL OR audit.model_sha256 IS DISTINCT FROM p_model_sha256
 OR audit.completion_state IS DISTINCT FROM 'current_open'
 OR audit.source_count IS DISTINCT FROM audit.actual_source_count
 OR audit.source_count IS DISTINCT FROM audit.canonical_source_count
 OR audit.unavailable_count IS DISTINCT FROM 0::bigint
 OR audit.source_set_sha256 IS DISTINCT FROM audit.canonical_source_set_sha256
 OR audit.row_count IS DISTINCT FROM audit.source_count*26
 OR (SELECT COUNT(*) FROM sync_fence.stats_primitive_sources s WHERE s.tenant_id=tenant
 AND s.game_id=p_game_id AND s.fact_version_id=p_fact_version_id) IS DISTINCT FROM audit.source_count
 OR audit.transaction_id IS DISTINCT FROM pg_catalog.pg_current_snapshot()::text
 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 -- 内容を再計算せず、保存済み唯一T5応答の全creditと実fact集合を双方向比較する。
 IF EXISTS(SELECT 1 FROM sync_fence.stats_primitive_sources s
 WHERE s.tenant_id=tenant AND s.game_id=p_game_id AND s.fact_version_id=p_fact_version_id
 AND s.evaluation_sha256 IS DISTINCT FROM pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
 s.metric_states::text,'UTF8')),'hex')) OR EXISTS(
 WITH expected_credits AS (
  SELECT s.source_event_id,m.key AS metric_id,(c.value->>'player_id')::uuid AS player_id,
  c.ordinality-1 AS credit_ordinal,'available'::text AS state,(c.value->>'quantity')::numeric AS amount
  FROM sync_fence.stats_primitive_sources s
  CROSS JOIN LATERAL pg_catalog.jsonb_each(s.metric_states->'metrics') m
  CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(m.value->'credits') WITH ORDINALITY c
  WHERE s.tenant_id=tenant AND s.game_id=p_game_id AND s.fact_version_id=p_fact_version_id
 ), actual_credits AS (
  SELECT f.source_event_id,f.metric_id,f.player_id,f.credit_ordinal,f.state,f.amount
  FROM sync_fence.stats_primitive_facts f WHERE f.tenant_id=tenant AND f.game_id=p_game_id
  AND f.fact_version_id=p_fact_version_id
 )
 (SELECT * FROM expected_credits EXCEPT SELECT * FROM actual_credits)
 UNION ALL (SELECT * FROM actual_credits EXCEPT SELECT * FROM expected_credits)
 ) THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;

 RETURN QUERY SELECT audit.fact_version_id,audit.revision,audit.source_set_sha256,
 audit.model_sha256,audit.source_count,audit.row_count,audit.transaction_id,audit.completion_state;

END;
$stats$;

ALTER FUNCTION stats_api.open_primitive_snapshot(uuid, uuid, text) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION stats_api.open_primitive_snapshot(uuid, uuid, text) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION stats_api.open_primitive_snapshot(uuid, uuid, text) TO pitchlog_app;
