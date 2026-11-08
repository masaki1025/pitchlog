-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:stats_api:read_writer_p3_play_export_page(uuid, uuid, uuid, uuid, uuid, bigint, integer, bytea, uuid, uuid, uuid, bigint, text)

CREATE FUNCTION stats_api.read_writer_p3_play_export_page(
 p_attempt_id uuid,p_phase_id uuid,p_game_id uuid,p_capsule_id uuid,
 p_change_event_id uuid,p_after_d1 bigint,p_page_size integer,p_binding_nonce bytea,
 p_prior_capsule_id uuid,p_prior_native_version_id uuid,p_prior_checkpoint_id uuid,
 p_prior_checkpoint_revision bigint,p_prior_checkpoint_digest text)
RETURNS TABLE(fact_version_id uuid,
 revision bigint,
 source_set_sha256 text,
 source_count bigint,
 completion_state text,
 transaction_id text,
 recording_generation bigint,
 d1 bigint,
 d2 bigint,
 source_event_id uuid,
 play_row_id uuid,
 slot_version bigint,
 play_row_version bigint,
 base_event_id uuid,
 source_fingerprint text,
 capsule_id uuid,
 capsule_source_set_digest text,
 capsule_stats_version_id uuid,
 target_d1 bigint,
 watermark bigint,
 item_digest text,
 original_play_row_id uuid,
 original_event_id uuid,
 state text,
 original_payload jsonb,
 original_history_entry jsonb,
 original_play_row jsonb,
 original_play_runners jsonb,
 payload jsonb,
 history_entry jsonb,
 play_row jsonb,
 play_runners jsonb,
 original_csv_json jsonb,
 original_snapshot_play_version bigint,
 original_snapshot_source_event_id uuid,
 original_snapshot_generation bigint,
 original_snapshot_sequence bigint,
 replacement_key text,
 replacement_label text,
 reference_captured_at timestamp with time zone,
 reference_id uuid)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_csv_read$
#variable_conflict use_column
DECLARE tenant uuid; own_xid text; generation bigint; target bigint;
 watermark_bound bigint; after_generation bigint; binding_device uuid;
 binding_d5 uuid; model_hash text := 'sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6';
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 IF session_user IS DISTINCT FROM 'pitchlog_app'
 OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner' OR tenant IS NULL
 OR p_attempt_id IS NULL OR p_phase_id IS NULL OR p_game_id IS NULL
 OR p_capsule_id IS NULL OR p_change_event_id IS NULL
 OR p_after_d1 IS NULL OR p_after_d1<0
 OR p_page_size IS NULL OR p_page_size<1 OR p_page_size>25
 OR p_binding_nonce IS NULL OR pg_catalog.octet_length(p_binding_nonce)<>32
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'off'
 THEN RAISE EXCEPTION 'P3 CSV writer source unavailable'
 USING ERRCODE='42501'; END IF;
 SELECT b.device_id,b.internal_generation,b.d5
 INTO STRICT binding_device,generation,binding_d5
 FROM sync_fence.writer_bindings b
 WHERE (b.tenant_id,b.game_id,b.attempt_id,b.phase_id)
 =(tenant,p_game_id,p_attempt_id,p_phase_id)
 AND b.state='open' AND b.transaction_id=own_xid
 AND b.expires_at>pg_catalog.clock_timestamp();
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,binding_device,p_game_id);
 SELECT c.target_d1,c.watermark INTO STRICT target,watermark_bound
 FROM sync_fence.p3_projection_capsules c
 JOIN sync_fence.p3_projection_heads h
 ON (h.tenant_id,h.game_id,h.internal_generation,h.capsule_id)
 =(c.tenant_id,c.game_id,c.internal_generation,c.id)
 JOIN public.operation_events e ON (e.tenant_id,e.game_id,e.id)
 =(c.tenant_id,c.game_id,c.change_event_id)
 WHERE (c.tenant_id,c.game_id,c.internal_generation,c.id,c.change_event_id)
 =(tenant,p_game_id,generation,p_capsule_id,p_change_event_id)
 AND c.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND e.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND e.event_kind='play_change' AND e.ledger_kind='accepted'
 AND e.d5=binding_d5 AND NOT e.is_tombstone
 AND e.retired_at IS NULL AND e.replaced_at IS NULL;
 IF p_after_d1>=watermark_bound THEN
 RAISE EXCEPTION 'P3 CSV writer page unavailable' USING ERRCODE='42501'; END IF;
 IF p_prior_native_version_id IS NULL OR p_prior_checkpoint_id IS NULL
 OR p_prior_checkpoint_revision IS NULL OR p_prior_checkpoint_digest IS NULL
 OR NOT EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions old
 WHERE (old.tenant_id,old.game_id,old.id)
 =(tenant,p_game_id,p_prior_native_version_id)
 AND NOT old.is_current AND old.invalidated_at IS NOT NULL
 AND old.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric))
 OR NOT EXISTS(SELECT 1 FROM sync_fence.p3_projection_capsules actual
 WHERE (actual.tenant_id,actual.game_id,actual.internal_generation,actual.id,
        actual.prior_checkpoint_id,actual.prior_checkpoint_revision,
        actual.prior_checkpoint_digest)
 =(tenant,p_game_id,generation,p_capsule_id,p_prior_checkpoint_id,
   p_prior_checkpoint_revision,p_prior_checkpoint_digest))
 OR (p_prior_capsule_id IS NOT NULL AND NOT EXISTS(
 SELECT 1 FROM sync_fence.p3_projection_capsules prior
 WHERE (prior.tenant_id,prior.game_id,prior.internal_generation,prior.id)
 =(tenant,p_game_id,generation,p_prior_capsule_id))) THEN
 RAISE EXCEPTION 'P3 CSV prior source unavailable' USING ERRCODE='42501'; END IF;
 after_generation:=CASE WHEN p_after_d1=0 THEN NULL ELSE generation END;
 RETURN QUERY WITH selected_sources AS (
WITH canonical_scope AS (
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
 WHERE (after_generation IS NULL OR
       (s.recording_generation,s.d1)>(after_generation,p_after_d1))
 ORDER BY s.recording_generation,s.d1 LIMIT p_page_size
)
SELECT v.id AS fact_version_id,v.revision,v.source_set_sha256,v.source_count,
 v.completion_state,pg_catalog.pg_current_snapshot()::text AS transaction_id,
 s.recording_generation,s.d1,s.d2,s.source_event_id,s.play_row_id,
 s.slot_version,s.play_row_version,s.base_event_id,s.source_fingerprint
FROM version_scope v JOIN member_health h ON h.id=v.id
LEFT JOIN bounded_members s ON true
WHERE h.actual_count=h.source_count
ORDER BY s.recording_generation,s.d1
)
SELECT s.fact_version_id,s.revision,s.source_set_sha256,s.source_count,
 s.completion_state,CAST(own_xid AS text) AS transaction_id,
 s.recording_generation,s.d1,s.d2,s.source_event_id,s.play_row_id,
 s.slot_version,s.play_row_version,s.base_event_id,s.source_fingerprint,
 c.id AS capsule_id,c.source_set_digest AS capsule_source_set_digest,
 c.stats_version_id AS capsule_stats_version_id,c.target_d1,c.watermark,
 i.item_digest,i.original_play_row_id,i.original_event_id,i.state,
 i.original_payload,i.original_history_entry,i.original_play_row,i.original_play_runners,
 i.payload,i.history_entry,i.play_row,i.play_runners,
 CASE WHEN prior_cap.id IS NOT NULL AND s.d1<=prior_cap.watermark
 THEN prior_csv.plays_csv_json ELSE original.plays_csv_json END AS original_csv_json,
 CASE WHEN prior_cap.id IS NOT NULL AND s.d1<=prior_cap.watermark
 THEN prior_csv.play_row_version ELSE original.play_version END
 AS original_snapshot_play_version,
 CASE WHEN prior_cap.id IS NOT NULL AND s.d1<=prior_cap.watermark
 THEN prior_csv.effective_event_id ELSE original.source_event_id END
 AS original_snapshot_source_event_id,
 CASE WHEN prior_cap.id IS NOT NULL AND s.d1<=prior_cap.watermark
 THEN prior_csv.internal_generation ELSE original.recording_generation END
 AS original_snapshot_generation,
 CASE WHEN prior_cap.id IS NOT NULL AND s.d1<=prior_cap.watermark
 THEN prior_item.d2 ELSE original.event_sequence END AS original_snapshot_sequence,
 v.key AS replacement_key,v.display_name AS replacement_label,
 pg_catalog.clock_timestamp() AS reference_captured_at,
 pg_catalog.gen_random_uuid() AS reference_id
FROM selected_sources s
JOIN sync_fence.p3_projection_heads h
 ON (h.tenant_id,h.game_id,h.internal_generation)
   =(tenant,p_game_id,s.recording_generation)
JOIN sync_fence.p3_projection_capsules c
 ON (c.tenant_id,c.game_id,c.internal_generation,c.id)
   =(h.tenant_id,h.game_id,h.internal_generation,h.capsule_id)
JOIN sync_fence.p3_projection_capsule_items i
 ON (i.tenant_id,i.game_id,i.internal_generation,i.capsule_id,i.d1,
     i.effective_event_id,i.effective_play_row_id)
   =(h.tenant_id,h.game_id,h.internal_generation,c.id,s.d1,s.source_event_id,s.play_row_id)
LEFT JOIN sync_fence.p3_projection_capsules prior_cap
 ON (prior_cap.tenant_id,prior_cap.game_id,prior_cap.internal_generation,prior_cap.id)
   =(h.tenant_id,h.game_id,h.internal_generation,p_prior_capsule_id)
LEFT JOIN sync_fence.p3_projection_capsule_items prior_item
 ON (prior_item.tenant_id,prior_item.game_id,prior_item.internal_generation,
     prior_item.capsule_id,prior_item.d1,prior_item.effective_event_id,
     prior_item.effective_play_row_id)
   =(h.tenant_id,h.game_id,h.internal_generation,prior_cap.id,s.d1,
     i.original_event_id,i.original_play_row_id)
 AND prior_item.payload=i.original_payload
 AND prior_item.history_entry=i.original_history_entry
 AND prior_item.play_row=i.original_play_row
 AND prior_item.play_runners=i.original_play_runners
LEFT JOIN sync_fence.play_export_p3_snapshots prior_csv
 ON (prior_csv.tenant_id,prior_csv.game_id,prior_csv.internal_generation,
     prior_csv.capsule_id,prior_csv.d1,prior_csv.item_digest,
     prior_csv.effective_event_id,prior_csv.effective_play_row_id)
   =(h.tenant_id,h.game_id,h.internal_generation,prior_cap.id,s.d1,
     prior_item.item_digest,prior_item.effective_event_id,
     prior_item.effective_play_row_id)
LEFT JOIN public.operation_events original_event
 ON (original_event.tenant_id,original_event.game_id,original_event.id)
   =(h.tenant_id,h.game_id,i.original_event_id)
 AND original_event.payload=i.original_payload
LEFT JOIN public.play_export_snapshots original
 ON (original.tenant_id,original.game_id,original.play_row_id,
     original.source_event_id)
   =(h.tenant_id,h.game_id,i.original_play_row_id,original_event.id)
 AND (p_prior_capsule_id IS NULL OR s.d1>prior_cap.watermark)
LEFT JOIN public.admin_vocabularies v
 ON i.d1=c.target_d1 AND v.key=i.play_row->>'batting_result_key'
 AND v.category='batting_result' AND NOT v.disabled
WHERE c.id=p_capsule_id AND c.change_event_id=p_change_event_id
 AND c.xmin::text::numeric
   =pg_catalog.mod(CAST(own_xid AS numeric),4294967296::numeric)
 AND c.stats_version_id=s.fact_version_id AND s.d1<=c.watermark
ORDER BY s.recording_generation,s.d1;
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,binding_device,p_game_id);
END;
$p3_csv_read$;
ALTER FUNCTION stats_api.read_writer_p3_play_export_page(uuid, uuid, uuid, uuid, uuid, bigint, integer, bytea, uuid, uuid, uuid, bigint, text) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION stats_api.read_writer_p3_play_export_page(uuid, uuid, uuid, uuid, uuid, bigint, integer, bytea, uuid, uuid, uuid, bigint, text) FROM PUBLIC,pitchlog_app,pitchlog_initial_actor,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor,pitchlog_initial_fn_owner,pitchlog_sync_binding_fn_owner;
GRANT EXECUTE ON FUNCTION stats_api.read_writer_p3_play_export_page(uuid, uuid, uuid, uuid, uuid, bigint, integer, bytea, uuid, uuid, uuid, bigint, text) TO pitchlog_app;
