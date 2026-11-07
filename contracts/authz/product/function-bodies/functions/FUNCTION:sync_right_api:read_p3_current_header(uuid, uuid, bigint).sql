-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:read_p3_current_header(uuid, uuid, bigint)

CREATE FUNCTION sync_right_api.read_p3_current_header(
p_tenant_id uuid,p_game_id uuid,p_generation bigint)
RETURNS TABLE(record_json text) LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_page_header$
#variable_conflict use_variable
DECLARE h sync_fence.p3_projection_heads%ROWTYPE;
 c sync_fence.p3_projection_capsules%ROWTYPE;
 cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE;
 v sync_fence.stats_fact_versions%ROWTYPE;
 e public.operation_events%ROWTYPE; ledger public.idempotency_ledger%ROWTYPE;
 progress sync_fence.p3_projection_page_progress%ROWTYPE;
 item_count bigint; source_count bigint; health record;
BEGIN
 IF session_user<>'pitchlog_app' OR current_user<>'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_game_id IS NULL OR p_generation IS NULL
 OR p_generation<=0 OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 THEN RAISE EXCEPTION 'P3 page header rejected' USING ERRCODE='42501'; END IF;
 SELECT x.* INTO h FROM sync_fence.p3_projection_heads x
 WHERE (x.tenant_id,x.game_id,x.internal_generation)=
 (p_tenant_id,p_game_id,p_generation);
 IF NOT FOUND THEN
 RETURN QUERY SELECT pg_catalog.jsonb_build_object('kind','none')::text;
 RETURN; END IF;
 SELECT x.* INTO STRICT c FROM sync_fence.p3_projection_capsules x
 WHERE (x.tenant_id,x.game_id,x.internal_generation,x.id)=
 (p_tenant_id,p_game_id,p_generation,h.capsule_id);
 IF c.watermark<=25 AND c.digest_format='p3-full-v1' THEN
 RETURN QUERY SELECT pg_catalog.jsonb_build_object('kind','p3-legacy')::text;
 RETURN; END IF;
 IF c.watermark<=25 OR c.digest_format<>'p3-page-chain-v2'
 OR h.source_set_digest IS DISTINCT FROM c.source_set_digest
 OR h.stats_version_id IS DISTINCT FROM c.stats_version_id
 THEN RAISE EXCEPTION 'P3 page header rejected' USING ERRCODE='42501'; END IF;
 SELECT x.* INTO STRICT progress FROM sync_fence.p3_projection_page_progress x
 WHERE (x.tenant_id,x.game_id,x.internal_generation,x.capsule_id)=
 (p_tenant_id,p_game_id,p_generation,c.id)
 AND x.state='finalized' AND x.item_count=c.watermark
 AND x.digest_format=c.digest_format
 AND x.capsule_header->>'source_set_digest'=c.source_set_digest
 AND x.stats_header->>'evaluation_set_digest'=c.stats_evaluation_set_digest;
 SELECT x.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints x
 WHERE (x.tenant_id,x.game_id,x.internal_generation)=
 (p_tenant_id,p_game_id,p_generation) AND x.state='current'
 AND x.content->>'formatVersion'='3';
 SELECT x.* INTO STRICT v FROM sync_fence.stats_fact_versions x
 WHERE (x.tenant_id,x.game_id,x.id)=
 (p_tenant_id,p_game_id,h.stats_version_id)
 AND x.is_current AND x.invalidated_at IS NULL
 AND x.source_count=cp.confirmed_watermark;
 SELECT x.* INTO STRICT e FROM public.operation_events x
 WHERE (x.tenant_id,x.game_id,x.id)=
 (p_tenant_id,p_game_id,c.change_event_id)
 AND x.event_kind='play_change' AND x.ledger_kind='accepted'
 AND NOT x.is_tombstone AND x.replaced_at IS NULL AND x.retired_at IS NULL
 AND x.target_generation=p_generation AND x.target_d1=c.target_d1
 AND x.expected_version=c.expected_version AND x.d5=c.d5;
 SELECT x.* INTO STRICT ledger FROM public.idempotency_ledger x
 WHERE (x.tenant_id,x.d5)=(p_tenant_id,c.d5)
 AND x.kind='accepted' AND x.retired_at IS NULL;
 SELECT pg_catalog.count(*) INTO item_count
 FROM sync_fence.p3_projection_capsule_items i
 WHERE (i.tenant_id,i.game_id,i.internal_generation,i.capsule_id)=
 (p_tenant_id,p_game_id,p_generation,c.id);
 SELECT pg_catalog.count(*) INTO source_count
 FROM sync_fence.stats_primitive_sources s
 WHERE (s.tenant_id,s.game_id,s.fact_version_id)=
 (p_tenant_id,p_game_id,v.id);
 IF item_count IS DISTINCT FROM c.watermark
 OR source_count IS DISTINCT FROM v.source_count
 OR cp.id IS DISTINCT FROM c.next_checkpoint_id
 OR cp.history_version IS DISTINCT FROM
 (c.next_checkpoint_content->>'history_version')::bigint
 OR cp.confirmed_watermark<c.watermark
 OR cp.applied_watermark IS DISTINCT FROM cp.confirmed_watermark
 OR cp.revision IS DISTINCT FROM
 c.next_checkpoint_revision+(cp.confirmed_watermark-c.watermark)
 OR (cp.confirmed_watermark=c.watermark AND
 (cp.content IS DISTINCT FROM c.next_checkpoint_content
 OR cp.content_digest IS DISTINCT FROM c.next_checkpoint_digest))
 OR cp.content->'storage_anchor' IS DISTINCT FROM
 c.next_checkpoint_content->'storage_anchor'
 OR v.model_sha256 IS DISTINCT FROM c.stats_model_sha256
 THEN RAISE EXCEPTION 'P3 page header rejected' USING ERRCODE='42501'; END IF;
 SELECT * INTO STRICT health FROM (WITH canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM public.games g
 WHERE g.tenant_id=p_tenant_id AND g.hidden_at IS NULL AND g.trashed_at IS NULL
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
)
SELECT COALESCE(ch.game_count,0) AS game_count,COALESCE(ch.canonical_source_count,0) AS canonical_source_count,COALESCE(ch.unavailable_count,0) AS unavailable_count,COALESCE(ch.canonical_source_set_sha256,encode(sha256(convert_to('accepted-play-slot-v1:empty','UTF8')),'hex')) AS canonical_source_set_sha256 FROM (VALUES(1)) singleton(n) LEFT JOIN canonical_health ch ON true) p3_page_health;
 IF health.game_count IS DISTINCT FROM 1 OR health.unavailable_count<>0
 OR health.canonical_source_count IS DISTINCT FROM v.source_count
 OR health.canonical_source_set_sha256 IS DISTINCT FROM v.source_set_sha256
 THEN RAISE EXCEPTION 'P3 page header rejected' USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT pg_catalog.jsonb_build_object(
 'kind','p3-paged-header','head',pg_catalog.to_jsonb(h),
 'capsule',pg_catalog.to_jsonb(c),'checkpoint',pg_catalog.to_jsonb(cp),
 'stats',pg_catalog.to_jsonb(v),'change_event',pg_catalog.to_jsonb(e),
 'change_ledger',pg_catalog.to_jsonb(ledger),
 'progress',pg_catalog.jsonb_build_object(
 'digest_format',progress.digest_format,'state',progress.state,
 'item_count',progress.item_count,'page_count',progress.page_count,
 'source_page_seal',progress.source_page_seal,
 'evaluation_page_seal',progress.evaluation_page_seal),
 'item_count',item_count,
 'source_count',source_count)::text;
END;
$p3_page_header$;
ALTER FUNCTION sync_right_api.read_p3_current_header(uuid,uuid,bigint)
 OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.read_p3_current_header(uuid,uuid,bigint)
 FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_right_api.read_p3_current_header(uuid,uuid,bigint)
 TO pitchlog_app;
