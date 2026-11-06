-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:stats_api:read_primitive_writer_state(uuid, uuid, uuid, text, bytea)

CREATE FUNCTION stats_api.read_primitive_writer_state(p_attempt_id uuid,p_phase_id uuid,p_source_event_id uuid,p_model_sha256 text,p_binding_nonce bytea)
RETURNS TABLE(revision bigint,source_set_sha256 text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $stats_writer_state$
#variable_conflict use_column
DECLARE tenant uuid; own_xid text; p_game_id uuid;
 binding sync_fence.writer_bindings%ROWTYPE;
 event_row public.operation_events%ROWTYPE;
 saved_play public.play_rows%ROWTYPE;
 checkpoint sync_fence.ordinary_pitch_checkpoints%ROWTYPE;
 series sync_fence.stats_fact_versions%ROWTYPE;
 stamp jsonb; variant text; provider text;
 checkpoint_id uuid; checkpoint_revision bigint;
 checkpoint_digest text; frame_digest text; current_source record;
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 IF session_user IS DISTINCT FROM 'pitchlog_app' OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'
 OR tenant IS NULL OR p_attempt_id IS NULL OR p_phase_id IS NULL OR p_source_event_id IS NULL
 OR p_binding_nonce IS NULL OR pg_catalog.octet_length(p_binding_nonce)<>32
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'off'
 OR p_model_sha256 IS DISTINCT FROM 'sha256:60ab45878fdfc868efc15ddb0f9b84d6ab0f3583519c48a2202e3d9c3abac59d'
 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 SELECT b.* INTO STRICT binding FROM sync_fence.writer_bindings b
 WHERE b.tenant_id=tenant AND b.attempt_id=p_attempt_id AND b.phase_id=p_phase_id
 AND b.state='open' AND b.transaction_id=own_xid AND b.expires_at>pg_catalog.clock_timestamp();
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,p_binding_nonce,binding.device_id,binding.game_id);
 p_game_id:=binding.game_id;
 IF NOT EXISTS(SELECT 1 FROM public.games g WHERE g.tenant_id=tenant AND g.id=p_game_id
 AND g.status='in_progress' AND g.hidden_at IS NULL AND g.trashed_at IS NULL) THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 SELECT e.* INTO STRICT event_row FROM public.operation_events e
 WHERE e.tenant_id=tenant AND e.game_id=p_game_id AND e.id=p_source_event_id
 AND e.generation=binding.internal_generation AND e.d5=binding.d5
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND e.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric);
 variant:=event_row.payload->>'formatVersion';
 IF event_row.payload#>'{calculation,response,ok}' IS DISTINCT FROM 'true'::jsonb
 OR event_row.payload#>>'{calculation,formatVersion}' IS DISTINCT FROM (CASE variant
 WHEN 'first-ball-play-v1' THEN 'first-ball-calculation-v1'
 WHEN 'ordinary-pitch-play-v1' THEN 'ordinary-pitch-calculation-v1'
 WHEN 'play-prefix-play-v2' THEN 'play-prefix-calculation-v2'
 WHEN 'play-prefix-play-v3' THEN (CASE WHEN event_row.payload#>>'{calculation,formatVersion}'='nonplay-prefix-calculation-v1' AND event_row.payload#>>'{calculation,request,source,formatVersion}'='nonplay-prefix-source-v1' THEN 'nonplay-prefix-calculation-v1' ELSE 'play-prefix-calculation-v3' END) END)
 OR variant NOT IN ('first-ball-play-v1','ordinary-pitch-play-v1','play-prefix-play-v2','play-prefix-play-v3')
 OR variant IS NULL THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 IF variant='first-ball-play-v1' THEN
  SELECT pg_catalog.to_jsonb(s) INTO STRICT stamp FROM sync_fence.first_ball_write_admissions s
  JOIN sync_fence.writer_bindings b USING(tenant_id,attempt_id,phase_id)
  JOIN sync_fence.writer_admissions wa USING(tenant_id,attempt_id,phase_id)
  WHERE s.tenant_id=tenant AND s.attempt_id=p_attempt_id AND s.phase_id=p_phase_id
  AND s.state='consumed' AND s.consumed_at IS NOT NULL AND s.source_event_id=p_source_event_id
  AND s.transaction_id=own_xid AND s.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
  AND wa.transaction_id=own_xid AND wa.lease_id=b.lease_id
  AND wa.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
  AND s.tenant_id IS NOT DISTINCT FROM b.tenant_id AND s.attempt_id IS NOT DISTINCT FROM b.attempt_id AND s.phase_id IS NOT DISTINCT FROM b.phase_id AND s.authority_id IS NOT DISTINCT FROM b.authority_id AND s.control_instance IS NOT DISTINCT FROM b.control_instance AND s.business_instance IS NOT DISTINCT FROM b.business_instance AND s.restore_epoch IS NOT DISTINCT FROM b.restore_epoch AND s.control_version IS NOT DISTINCT FROM b.control_version AND s.issuer IS NOT DISTINCT FROM b.issuer AND s.lease_id IS NOT DISTINCT FROM b.lease_id AND s.device_id IS NOT DISTINCT FROM b.device_id AND s.game_id IS NOT DISTINCT FROM b.game_id AND s.wire_d4 IS NOT DISTINCT FROM b.wire_d4 AND s.internal_generation IS NOT DISTINCT FROM b.internal_generation AND s.recovery_generation IS NOT DISTINCT FROM b.recovery_generation AND s.codec_version IS NOT DISTINCT FROM b.codec_version AND s.request_fingerprint IS NOT DISTINCT FROM b.request_fingerprint AND s.d5 IS NOT DISTINCT FROM b.d5 AND s.event_fingerprint IS NOT DISTINCT FROM b.event_fingerprint AND s.system_identifier IS NOT DISTINCT FROM b.system_identifier AND s.database_oid IS NOT DISTINCT FROM b.database_oid AND s.postmaster_started_at IS NOT DISTINCT FROM b.postmaster_started_at AND s.backend_pid IS NOT DISTINCT FROM b.backend_pid AND s.backend_start IS NOT DISTINCT FROM b.backend_start AND s.transaction_id IS NOT DISTINCT FROM b.transaction_id AND s.nonce_digest IS NOT DISTINCT FROM b.nonce_digest AND s.expires_at IS NOT DISTINCT FROM b.expires_at;
  IF EXISTS(SELECT 1 FROM sync_fence.ordinary_pitch_write_admissions o
   WHERE o.tenant_id=tenant AND o.attempt_id=p_attempt_id AND o.phase_id=p_phase_id
   AND o.state IN ('device_verified','right_verified','evaluated','consumed')) THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
  checkpoint_id:=NULL; checkpoint_revision:=NULL; checkpoint_digest:=NULL; frame_digest:=NULL;
  provider:='first_ball';
 ELSE
  SELECT pg_catalog.to_jsonb(s) INTO STRICT stamp FROM sync_fence.ordinary_pitch_write_admissions s
  JOIN sync_fence.writer_bindings b USING(tenant_id,attempt_id,phase_id)
  JOIN sync_fence.writer_admissions wa USING(tenant_id,attempt_id,phase_id)
  WHERE s.tenant_id=tenant AND s.attempt_id=p_attempt_id AND s.phase_id=p_phase_id
  AND s.state='consumed' AND s.consumed_at IS NOT NULL AND s.source_event_id=p_source_event_id
  AND s.transaction_id=own_xid AND s.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
  AND wa.transaction_id=own_xid AND wa.lease_id=b.lease_id
  AND wa.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
  AND s.tenant_id IS NOT DISTINCT FROM b.tenant_id AND s.attempt_id IS NOT DISTINCT FROM b.attempt_id AND s.phase_id IS NOT DISTINCT FROM b.phase_id AND s.authority_id IS NOT DISTINCT FROM b.authority_id AND s.control_instance IS NOT DISTINCT FROM b.control_instance AND s.business_instance IS NOT DISTINCT FROM b.business_instance AND s.restore_epoch IS NOT DISTINCT FROM b.restore_epoch AND s.control_version IS NOT DISTINCT FROM b.control_version AND s.issuer IS NOT DISTINCT FROM b.issuer AND s.lease_id IS NOT DISTINCT FROM b.lease_id AND s.device_id IS NOT DISTINCT FROM b.device_id AND s.game_id IS NOT DISTINCT FROM b.game_id AND s.wire_d4 IS NOT DISTINCT FROM b.wire_d4 AND s.internal_generation IS NOT DISTINCT FROM b.internal_generation AND s.recovery_generation IS NOT DISTINCT FROM b.recovery_generation AND s.codec_version IS NOT DISTINCT FROM b.codec_version AND s.request_fingerprint IS NOT DISTINCT FROM b.request_fingerprint AND s.d5 IS NOT DISTINCT FROM b.d5 AND s.event_fingerprint IS NOT DISTINCT FROM b.event_fingerprint AND s.system_identifier IS NOT DISTINCT FROM b.system_identifier AND s.database_oid IS NOT DISTINCT FROM b.database_oid AND s.postmaster_started_at IS NOT DISTINCT FROM b.postmaster_started_at AND s.backend_pid IS NOT DISTINCT FROM b.backend_pid AND s.backend_start IS NOT DISTINCT FROM b.backend_start AND s.transaction_id IS NOT DISTINCT FROM b.transaction_id AND s.nonce_digest IS NOT DISTINCT FROM b.nonce_digest AND s.expires_at IS NOT DISTINCT FROM b.expires_at;
  IF EXISTS(SELECT 1 FROM sync_fence.first_ball_write_admissions f
   WHERE f.tenant_id=tenant AND f.attempt_id=p_attempt_id AND f.phase_id=p_phase_id
   AND f.state IN ('device_verified','right_verified','consumed')) THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
  SELECT c.* INTO STRICT checkpoint FROM sync_fence.ordinary_pitch_checkpoints c
  WHERE c.tenant_id=tenant AND c.game_id=p_game_id AND c.internal_generation=binding.internal_generation
  AND c.id=(stamp->>'checkpoint_id')::uuid AND c.state='current'
  AND c.content=(CASE WHEN variant='play-prefix-play-v3' AND event_row.payload#>>'{calculation,formatVersion}'='nonplay-prefix-calculation-v1' AND event_row.payload#>>'{calculation,request,source,formatVersion}'='nonplay-prefix-source-v1' AND stamp->'next_checkpoint_content'->>'formatVersion'='nonplay-normal-storage-v1' THEN stamp->'next_checkpoint_content'->'checkpoint' ELSE stamp->'next_checkpoint_content' END) AND c.content_digest=(CASE WHEN variant='play-prefix-play-v3' AND event_row.payload#>>'{calculation,formatVersion}'='nonplay-prefix-calculation-v1' AND event_row.payload#>>'{calculation,request,source,formatVersion}'='nonplay-prefix-source-v1' AND stamp->'next_checkpoint_content'->>'formatVersion'='nonplay-normal-storage-v1' THEN stamp->'next_checkpoint_content'->'checkpoint'->'ref'->>'digest' ELSE stamp->'next_checkpoint_content'->>'content_digest' END)
  AND c.revision=(CASE WHEN variant='play-prefix-play-v3' AND event_row.payload#>>'{calculation,formatVersion}'='nonplay-prefix-calculation-v1' AND event_row.payload#>>'{calculation,request,source,formatVersion}'='nonplay-prefix-source-v1' AND stamp->'next_checkpoint_content'->>'formatVersion'='nonplay-normal-storage-v1' THEN (stamp->'next_checkpoint_content'->'checkpoint'->'ref'->>'revision')::bigint ELSE (stamp->'next_checkpoint_content'->>'revision')::bigint END)
  AND c.history_version=(CASE WHEN variant='play-prefix-play-v3' AND event_row.payload#>>'{calculation,formatVersion}'='nonplay-prefix-calculation-v1' AND event_row.payload#>>'{calculation,request,source,formatVersion}'='nonplay-prefix-source-v1' AND stamp->'next_checkpoint_content'->>'formatVersion'='nonplay-normal-storage-v1' THEN (stamp->'next_checkpoint_content'->'checkpoint'->'content'->>'storageHistoryEpoch')::bigint ELSE (stamp->'next_checkpoint_content'->>'history_version')::bigint END)
  AND c.confirmed_watermark=event_row.d1 AND c.applied_watermark=event_row.d1
  AND c.saved_at=(stamp->>'consumed_at')::timestamptz
  AND c.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric);
  IF stamp->>'artifact_sha256' IS DISTINCT FROM event_row.payload#>>'{calculation,artifactSha256}'
  OR stamp->>'frame_digest' IS NULL OR stamp->>'frame_digest' !~ '^[a-f0-9]{64}$'
  OR stamp->>'source_d1' IS DISTINCT FROM event_row.d1::text
  OR stamp->>'source_d2' IS DISTINCT FROM event_row.d2::text
  THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
  checkpoint_id:=checkpoint.id; checkpoint_revision:=checkpoint.revision;
  checkpoint_digest:=checkpoint.content_digest; frame_digest:=stamp->>'frame_digest'; provider:='ordinary';
 END IF;
 SELECT p.* INTO STRICT saved_play FROM public.play_rows p
 WHERE p.tenant_id=tenant AND p.game_id=p_game_id AND p.source_event_id=p_source_event_id
 AND p.id=(stamp->>'play_row_id')::uuid AND p.hidden_at IS NULL
 AND p.import_batch_id IS NULL AND p.legacy_row_identifier IS NULL AND NOT p.migration_unverified
 AND p.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric);
 IF provider='ordinary' AND pg_catalog.to_jsonb(saved_play) IS DISTINCT FROM stamp->'expected_play_row'
 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.idempotency_ledger l WHERE l.tenant_id=tenant
 AND l.d5=binding.d5 AND l.kind='accepted' AND l.source_fingerprint=binding.event_fingerprint
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND l.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric))
 OR NOT EXISTS(SELECT 1 FROM public.recording_generations r WHERE r.tenant_id=tenant AND r.game_id=p_game_id
 AND r.generation=binding.internal_generation AND r.kind='normal' AND r.holder_device=binding.device_id::text
 AND r.revoked_at IS NULL AND r.retired_at IS NULL AND r.recovery_generation=binding.recovery_generation
 AND r.confirmed_watermark=event_row.d1 AND r.applied_prefix=event_row.d1)
 OR NOT EXISTS(SELECT 1 FROM public.rg1_restore_gate g WHERE g.singleton_id=1 AND g.state='open'
 AND g.recovery_generation=binding.recovery_generation)
 OR NOT EXISTS(SELECT 1 FROM public.trusted_devices d WHERE d.tenant_id=tenant AND d.device_id=binding.device_id AND d.revoked_at IS NULL)
 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 SELECT * INTO STRICT current_source FROM (WITH canonical_scope AS (
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
SELECT c.* FROM canonical_s c WHERE c.source_event_id=p_source_event_id AND c.source_state='included') canonical_current;
 IF current_source.recording_generation IS DISTINCT FROM event_row.generation
 OR current_source.d1 IS DISTINCT FROM event_row.d1 OR current_source.d2 IS DISTINCT FROM event_row.d2
 OR current_source.slot_version IS DISTINCT FROM 1::bigint
 OR current_source.play_row_id IS DISTINCT FROM saved_play.id OR current_source.play_row_version IS DISTINCT FROM saved_play.version
 OR current_source.source_fingerprint IS DISTINCT FROM binding.event_fingerprint
 OR current_source.artifact_sha256 IS DISTINCT FROM event_row.payload#>>'{calculation,artifactSha256}'
 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 BEGIN
  SELECT v.* INTO STRICT series FROM sync_fence.stats_fact_versions v
  WHERE v.tenant_id=tenant AND v.game_id=p_game_id
  AND v.model_sha256=p_model_sha256 AND v.is_current FOR UPDATE;
 EXCEPTION WHEN NO_DATA_FOUND THEN
  IF EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions v
   WHERE v.tenant_id=tenant AND v.game_id=p_game_id
   AND v.model_sha256=p_model_sha256) THEN
   RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501';
  END IF;
  RETURN QUERY SELECT 0::bigint,NULL::text;
  RETURN;
 END;
 IF series.is_current IS DISTINCT FROM true
 OR series.invalidated_at IS NOT NULL
 OR series.completion_state IS DISTINCT FROM 'current_open'
 OR series.revision IS NULL OR series.revision<1
 OR series.source_set_sha256 IS NULL
 OR series.source_set_sha256 !~ '^[a-f0-9]{64}$'
 OR series.rule_sha256 IS NULL OR series.rule_sha256 !~ '^[a-f0-9]{64}$'
 OR series.source_count IS NULL OR series.source_count<0
 OR series.t5_artifact_set_sha256 IS DISTINCT FROM '28af30fd1b1300c805b7dcb243fc7b32ab9d6db9fc10c38bdcbc63fa85c3a0de' THEN
  RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501';
 END IF;
 RETURN QUERY SELECT series.revision,series.source_set_sha256;
END;
$stats_writer_state$;

ALTER FUNCTION stats_api.read_primitive_writer_state(uuid, uuid, uuid, text, bytea) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION stats_api.read_primitive_writer_state(uuid, uuid, uuid, text, bytea) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION stats_api.read_primitive_writer_state(uuid, uuid, uuid, text, bytea) TO pitchlog_app;
