-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:stats_api:read_writer_p3_play_export_prior(uuid, uuid, uuid, uuid, uuid, bytea, uuid, bigint, text, bigint)

CREATE FUNCTION stats_api.read_writer_p3_play_export_prior(
 p_attempt_id uuid,p_phase_id uuid,p_game_id uuid,p_capsule_id uuid,
 p_change_event_id uuid,p_binding_nonce bytea,p_checkpoint_id uuid,
 p_checkpoint_revision bigint,p_checkpoint_digest text,p_watermark bigint)
RETURNS TABLE(prior_capsule_id uuid,prior_native_version_id uuid,
 prior_checkpoint_id uuid,prior_checkpoint_revision bigint,
 prior_checkpoint_digest text,transaction_id text,
 game_source_count bigint,generation_source_count bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_csv_prior$
#variable_conflict use_column
DECLARE tenant uuid; own_xid text; binding_device uuid; generation bigint;
 model_hash text := 'sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6';
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 IF session_user IS DISTINCT FROM 'pitchlog_app'
 OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner' OR tenant IS NULL
 OR p_attempt_id IS NULL OR p_phase_id IS NULL OR p_game_id IS NULL
 OR p_capsule_id IS NULL OR p_change_event_id IS NULL
 OR p_checkpoint_id IS NULL OR p_checkpoint_revision IS NULL
 OR p_checkpoint_revision<1 OR p_checkpoint_digest IS NULL
 OR p_checkpoint_digest !~ '^[a-f0-9]{64}$' OR p_watermark IS NULL OR p_watermark<1
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
 RETURN QUERY WITH actual_source AS (WITH canonical_scope AS (
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
), version_scope AS (
 SELECT v.* FROM sync_fence.stats_fact_versions v
 JOIN canonical_health h ON (h.tenant_id,h.game_id)=(v.tenant_id,v.game_id)
 WHERE v.tenant_id=tenant AND v.game_id=p_game_id
   AND v.model_sha256=model_hash AND v.is_current AND v.invalidated_at IS NULL
   AND v.completion_state IN ('current_open','confirmed_ended')
   AND h.game_count=1 AND h.unavailable_count=0
   AND h.canonical_source_count=v.source_count
   AND h.canonical_source_set_sha256=v.source_set_sha256
), candidate_members AS (
SELECT s.* FROM sync_fence.stats_primitive_sources s
 JOIN canonical_s c ON c.tenant_id=s.tenant_id AND c.game_id=s.game_id
   AND c.source_event_id=s.source_event_id AND c.recording_generation=s.recording_generation
   AND c.d1=s.d1 AND c.d2=s.d2 AND c.slot_version=s.slot_version
   AND c.play_row_id=s.play_row_id AND c.play_row_version=s.play_row_version
   AND c.source_fingerprint=s.source_fingerprint AND c.artifact_sha256=s.artifact_sha256
   AND c.source_state='included'
WHERE s.tenant_id=tenant AND s.game_id=p_game_id AND s.fact_version_id=(SELECT id FROM version_scope)
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
 WHERE s.recording_generation=generation AND (NULL::bigint IS NULL OR
       (s.recording_generation,s.d1)>(NULL::bigint,NULL::bigint))
 ORDER BY s.recording_generation,s.d1 LIMIT 1
)
SELECT v.id AS fact_version_id,v.revision,v.source_set_sha256,v.source_count,
 (SELECT COUNT(*) FROM source_members g WHERE g.recording_generation=generation) AS generation_source_count,
 v.completion_state,pg_catalog.pg_current_snapshot()::text AS transaction_id,
 s.recording_generation,s.d1,s.d2,s.source_event_id,s.play_row_id,
 s.slot_version,s.play_row_version,s.base_event_id,s.source_fingerprint
FROM version_scope v JOIN member_health h ON h.id=v.id
LEFT JOIN bounded_members s ON true
WHERE h.actual_count=h.source_count
ORDER BY s.recording_generation,s.d1)
 SELECT h.capsule_id,s.fact_version_id,cp.id,cp.revision,cp.content_digest,own_xid,
 s.source_count,s.generation_source_count
 FROM actual_source s
 JOIN sync_fence.ordinary_pitch_checkpoints cp
 ON (cp.tenant_id,cp.game_id,cp.id,cp.revision,cp.content_digest)
 =(tenant,p_game_id,p_checkpoint_id,p_checkpoint_revision,p_checkpoint_digest)
 LEFT JOIN sync_fence.p3_projection_heads h
 ON (h.tenant_id,h.game_id,h.internal_generation)=(tenant,p_game_id,generation)
 WHERE s.generation_source_count=p_watermark;
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,binding_device,p_game_id);
END;
$p3_csv_prior$;
ALTER FUNCTION stats_api.read_writer_p3_play_export_prior(uuid, uuid, uuid, uuid, uuid, bytea, uuid, bigint, text, bigint) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION stats_api.read_writer_p3_play_export_prior(uuid, uuid, uuid, uuid, uuid, bytea, uuid, bigint, text, bigint) FROM PUBLIC,pitchlog_app,pitchlog_initial_actor,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor,pitchlog_initial_fn_owner,pitchlog_sync_binding_fn_owner;
GRANT EXECUTE ON FUNCTION stats_api.read_writer_p3_play_export_prior(uuid, uuid, uuid, uuid, uuid, bytea, uuid, bigint, text, bigint) TO pitchlog_app;
