-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:finalize_p3_projection_page(uuid, uuid, uuid, bytea, uuid, uuid, uuid)

CREATE FUNCTION sync_right_api.finalize_p3_projection_page(
p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding_nonce bytea,p_device_id uuid,p_game_id uuid,p_capsule_id uuid)
RETURNS TABLE(capsule_id uuid,checkpoint_digest text,evaluation_set_digest text,
 stats_version_id uuid) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_page_finalize$
#variable_conflict use_column
DECLARE binding record; p sync_fence.p3_projection_page_progress%ROWTYPE;
 c jsonb; t jsonb; item jsonb; effective_eval jsonb;
 old_cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE;
 old_stats sync_fence.stats_fact_versions%ROWTYPE;
 old_source sync_fence.stats_primitive_sources%ROWTYPE;
 lifecycle sync_fence.game_lifecycle_heads%ROWTYPE;
 game_status text; health record; row_item record; metric record; credit record;
 own_xid text; now_at timestamptz; new_id uuid;
 source_digest text; evaluation_digest text; new_artifact text;
 member_count bigint; matched_count bigint; credit_ordinal bigint;
 complete_order boolean; common_keys text[]; source_keys text[];
BEGIN
 IF session_user<>'pitchlog_app' OR current_user<>'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_attempt_id IS NULL OR p_phase_id IS NULL
 OR p_device_id IS NULL OR p_game_id IS NULL OR p_capsule_id IS NULL
 OR p_binding_nonce IS NULL OR pg_catalog.octet_length(p_binding_nonce)<>32
 OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'off'
 THEN RAISE EXCEPTION 'P3 page finalize rejected' USING ERRCODE='42501'; END IF;
 PERFORM sync_fence_api.assert_writer_binding(p_tenant_id,p_attempt_id,p_phase_id,
 p_binding_nonce,p_device_id,p_game_id);
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 SELECT b.* INTO STRICT binding FROM sync_fence_api.read_p3_writer_binding(
 p_tenant_id,p_attempt_id,p_phase_id,p_binding_nonce,p_device_id,p_game_id) b;
 SELECT x.* INTO STRICT p FROM sync_fence.p3_projection_page_progress x
 WHERE (x.tenant_id,x.game_id,x.internal_generation,x.capsule_id)=
 (p_tenant_id,p_game_id,binding.internal_generation,p_capsule_id)
 AND (x.attempt_id,x.phase_id,x.device_id,x.binding_nonce,x.transaction_id)=
 (p_attempt_id,p_phase_id,p_device_id,p_binding_nonce,own_xid)
 AND x.state='building' AND x.item_count=x.watermark AND x.watermark>25
 AND x.d5=binding.d5 FOR UPDATE;
 c:=p.capsule_header; t:=p.stats_header;
 IF c->>'digest_format' IS DISTINCT FROM 'p3-page-chain-v2'
 OR c->>'item_chain' IS DISTINCT FROM p.source_page_seal
 OR t->>'evaluation_chain' IS DISTINCT FROM p.evaluation_page_seal
 OR c->>'page_seal' !~ '^[a-f0-9]{64}$'
 OR c->>'ledger_fingerprint' !~ '^[a-f0-9]{64}$'
 THEN RAISE EXCEPTION 'P3 page finalize rejected' USING ERRCODE='42501'; END IF;
 source_digest:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
 'p3-page-chain-v2:'||p_capsule_id::text||':'||
 (c->>'change_event_id')||':'||(c->>'previous_checkpoint_digest')||':'||
 (c->'next_checkpoint'->>'content_digest')||':'||p.watermark::text||':'||
 p.source_page_seal,'UTF8')),'hex');
 evaluation_digest:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
 'p3-stats-chain-v2:'||p_capsule_id::text||':sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6:'||
 source_digest||':'||p.evaluation_page_seal,'UTF8')),'hex');
 IF source_digest IS DISTINCT FROM c->>'source_set_digest'
 OR evaluation_digest IS DISTINCT FROM t->>'evaluation_set_digest'
 THEN RAISE EXCEPTION 'P3 page finalize rejected' USING ERRCODE='42501'; END IF;
 SELECT pg_catalog.count(*),
 pg_catalog.bool_and(x.d1=x.ordinal AND
 (x.ordinal=1 OR x.d2>x.previous_d2))
 INTO member_count,complete_order FROM (
 SELECT r.d1,r.d2,pg_catalog.row_number() OVER (ORDER BY r.d1) ordinal,
 pg_catalog.lag(r.d2) OVER (ORDER BY r.d1) previous_d2
 FROM sync_fence.p3_projection_page_rows r
 WHERE (r.tenant_id,r.game_id,r.internal_generation,r.capsule_id)=
 (p_tenant_id,p_game_id,p.internal_generation,p_capsule_id)
 AND (r.attempt_id,r.phase_id,r.device_id,r.binding_nonce,r.transaction_id,
 r.d5,r.ledger_fingerprint)=
 (p_attempt_id,p_phase_id,p_device_id,p_binding_nonce,own_xid,binding.d5,
 c->>'ledger_fingerprint')) x;
 IF member_count IS DISTINCT FROM p.watermark OR complete_order IS DISTINCT FROM true
 OR NOT EXISTS(SELECT 1 FROM sync_fence.p3_projection_page_rows r
 WHERE (r.tenant_id,r.game_id,r.internal_generation,r.capsule_id,r.d1)=
 (p_tenant_id,p_game_id,p.internal_generation,p_capsule_id,p.target_d1)
 AND r.effective_event_id=(c->>'change_event_id')::uuid)
 THEN RAISE EXCEPTION 'P3 page finalize rejected' USING ERRCODE='42501'; END IF;
 SELECT cp.* INTO STRICT old_cp FROM sync_fence.ordinary_pitch_checkpoints cp
 WHERE (cp.tenant_id,cp.game_id,cp.internal_generation)=
 (p_tenant_id,p_game_id,p.internal_generation)
 AND cp.id=(c->>'previous_checkpoint_id')::uuid
 AND cp.revision=(c->>'previous_checkpoint_revision')::bigint
 AND cp.content_digest=c->>'previous_checkpoint_digest'
 AND cp.content=c->'previous_checkpoint' AND cp.state='current'
 AND cp.confirmed_watermark=p.watermark FOR UPDATE;
 SELECT v.* INTO STRICT old_stats FROM sync_fence.stats_fact_versions v
 WHERE (v.tenant_id,v.game_id,v.id)=(p_tenant_id,p_game_id,p.old_stats_version_id)
 AND v.is_current AND v.invalidated_at IS NULL AND v.source_count=p.watermark
 AND v.model_sha256='sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6' AND v.t5_artifact_set_sha256='b551ca128619674a5fc87efe44eba1acae329ed5979353600149dd4226e8dad2';
 SELECT g.status INTO STRICT game_status FROM public.games g
 WHERE (g.tenant_id,g.id)=(p_tenant_id,p_game_id)
 AND g.status IN ('in_progress','finished') AND g.hidden_at IS NULL
 AND g.trashed_at IS NULL AND g.import_batch_id IS NULL;
 IF (SELECT pg_catalog.count(*) FROM public.recording_generations r
 WHERE (r.tenant_id,r.game_id,r.generation)=
 (p_tenant_id,p_game_id,p.internal_generation) AND r.kind='normal'
 AND r.holder_device=p_device_id::text AND r.revoked_at IS NULL
 AND r.retired_at IS NULL AND r.recovery_generation=(SELECT gate.recovery_generation
 FROM public.rg1_restore_gate gate WHERE gate.singleton_id=1 AND gate.state='open'))<>1
 OR (game_status='finished') IS DISTINCT FROM
 (old_stats.completion_state='confirmed_ended')
 THEN RAISE EXCEPTION 'P3 page finalize rejected' USING ERRCODE='42501'; END IF;
 IF game_status='finished' THEN
 SELECT h.* INTO STRICT lifecycle FROM sync_fence.game_lifecycle_heads h
 WHERE (h.tenant_id,h.game_id)=(p_tenant_id,p_game_id)
 AND h.is_finished AND h.active_stats_version_id=old_stats.id
 AND h.active_receipt_id=old_stats.completion_receipt_id
 AND h.active_receipt_id=old_stats.public_pointer_receipt_id FOR UPDATE;
 END IF;
 new_id:=pg_catalog.gen_random_uuid();now_at:=pg_catalog.clock_timestamp();
 INSERT INTO sync_fence.p3_projection_capsules(
 tenant_id,game_id,internal_generation,id,change_event_id,d5,target_d1,
 expected_version,prior_checkpoint_id,prior_checkpoint_revision,
 prior_checkpoint_digest,prior_checkpoint_content,next_checkpoint_id,
 next_checkpoint_revision,next_checkpoint_digest,next_checkpoint_content,
 source_set_digest,stats_evaluation_set_digest,stats_model_sha256,digest_format,
 stats_version_id,watermark,created_at)
 VALUES(p_tenant_id,p_game_id,p.internal_generation,p_capsule_id,
 (c->>'change_event_id')::uuid,binding.d5,p.target_d1,1,old_cp.id,
 old_cp.revision,old_cp.content_digest,old_cp.content,
 (c->'next_checkpoint'->>'id')::uuid,
 (c->'next_checkpoint'->>'revision')::bigint,
 c->'next_checkpoint'->>'content_digest',c->'next_checkpoint',
 source_digest,evaluation_digest,'sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6','p3-page-chain-v2',
 new_id,p.watermark,now_at);
 INSERT INTO sync_fence.p3_projection_capsule_items(
 tenant_id,game_id,internal_generation,capsule_id,d1,d2,state,
 original_event_id,effective_event_id,original_play_row_id,effective_play_row_id,
 original_payload,original_history_entry,original_play_row,original_play_runners,
 payload,history_entry,play_row,play_runners,item_digest)
 SELECT r.tenant_id,r.game_id,r.internal_generation,r.capsule_id,r.d1,r.d2,
 r.item->>'state',r.original_event_id,r.effective_event_id,
 (r.item->>'original_play_row_id')::uuid,r.effective_play_row_id,
 r.item->'original_payload',r.item->'original_history_entry',
 r.item->'original_play_row',r.item->'original_play_runners',
 r.item->'payload',r.item->'history_entry',r.item->'play_row',
 r.item->'play_runners',r.item_digest
 FROM sync_fence.p3_projection_page_rows r
 WHERE (r.tenant_id,r.game_id,r.internal_generation,r.capsule_id)=
 (p_tenant_id,p_game_id,p.internal_generation,p_capsule_id)
 ORDER BY r.d1;
 INSERT INTO sync_fence.p3_projection_heads(
 tenant_id,game_id,internal_generation,capsule_id,revision,
 source_set_digest,stats_version_id,updated_at)
 VALUES(p_tenant_id,p_game_id,p.internal_generation,p_capsule_id,1,
 source_digest,new_id,now_at);
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
SELECT COALESCE(ch.game_count,0) AS game_count,COALESCE(ch.canonical_source_count,0) AS canonical_source_count,COALESCE(ch.unavailable_count,0) AS unavailable_count,COALESCE(ch.canonical_source_set_sha256,encode(sha256(convert_to('accepted-play-slot-v1:empty','UTF8')),'hex')) AS canonical_source_set_sha256 FROM (VALUES(1)) singleton(n) LEFT JOIN canonical_health ch ON true) actual_p3_health;
 IF health.game_count IS DISTINCT FROM 1 OR health.unavailable_count<>0
 OR health.canonical_source_count IS DISTINCT FROM p.watermark
 OR health.canonical_source_set_sha256 !~ '^[a-f0-9]{64}$'
 THEN RAISE EXCEPTION 'P3 page finalize rejected' USING ERRCODE='42501'; END IF;
 UPDATE sync_fence.stats_fact_versions v SET is_current=false,invalidated_at=now_at
 WHERE (v.tenant_id,v.game_id,v.id)=(p_tenant_id,p_game_id,old_stats.id)
 AND v.is_current AND v.invalidated_at IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'P3 page finalize rejected'
 USING ERRCODE='42501'; END IF;
 INSERT INTO sync_fence.stats_fact_versions(
 tenant_id,game_id,id,model_sha256,rule_sha256,t5_artifact_set_sha256,
 source_set_sha256,source_count,revision,last_generation,last_d1,last_d2,
 updated_at,computed_metric_keys,is_current,completion_state,
 completion_receipt_id,public_pointer_receipt_id,created_at,invalidated_at)
 SELECT p_tenant_id,p_game_id,new_id,v.model_sha256,v.rule_sha256,
 v.t5_artifact_set_sha256,health.canonical_source_set_sha256,p.watermark,
 v.revision+1,v.last_generation,v.last_d1,v.last_d2,now_at,
 v.computed_metric_keys,true,v.completion_state,v.completion_receipt_id,
 v.public_pointer_receipt_id,now_at,NULL
 FROM sync_fence.stats_fact_versions v WHERE (v.tenant_id,v.game_id,v.id)=
 (p_tenant_id,p_game_id,old_stats.id);
 FOR row_item IN SELECT r.* FROM sync_fence.p3_projection_page_rows r
 WHERE (r.tenant_id,r.game_id,r.internal_generation,r.capsule_id)=
 (p_tenant_id,p_game_id,p.internal_generation,p_capsule_id)
 ORDER BY r.d1 LOOP
 item:=row_item.item;effective_eval:=row_item.evaluation;
 IF pg_catalog.jsonb_typeof(effective_eval->'metrics') IS DISTINCT FROM 'object'
 OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
 pg_catalog.jsonb_object_keys(effective_eval) k) IS DISTINCT FROM
 ARRAY['decisions','metrics','native_rule_sha256','pa_row','selected',
 'source_event_id']::text[]
 THEN RAISE EXCEPTION 'P3 page finalize rejected' USING ERRCODE='42501'; END IF;
 SELECT s.* INTO STRICT old_source FROM sync_fence.stats_primitive_sources s
 WHERE (s.tenant_id,s.game_id,s.fact_version_id,s.source_event_id)=
 (p_tenant_id,p_game_id,old_stats.id,row_item.original_event_id)
 AND s.recording_generation=p.internal_generation AND s.d1=row_item.d1;
 IF effective_eval->>'native_rule_sha256' IS DISTINCT FROM old_source.rule_sha256
 OR row_item.original_evaluation IS DISTINCT FROM old_source.metric_states
 THEN RAISE EXCEPTION 'P3 page finalize rejected' USING ERRCODE='42501'; END IF;
 new_artifact:=item->'payload'->'calculation'->>'artifactSha256';
 IF new_artifact IS NULL OR new_artifact !~ '^[a-f0-9]{64}$'
 THEN RAISE EXCEPTION 'P3 page finalize rejected' USING ERRCODE='42501'; END IF;
 SELECT COALESCE(pg_catalog.array_agg(key ORDER BY key),'{}'::text[])
 INTO source_keys FROM pg_catalog.jsonb_each(effective_eval->'metrics')
 WHERE value->>'state'='available';
 IF row_item.d1=1 THEN common_keys:=source_keys;
 ELSE common_keys:=ARRAY(SELECT k FROM pg_catalog.unnest(common_keys) k
 WHERE k=ANY(source_keys) ORDER BY k); END IF;
 INSERT INTO sync_fence.stats_primitive_sources(
 tenant_id,game_id,fact_version_id,source_event_id,play_row_id,
 recording_generation,d1,d2,slot_version,play_row_version,provider_kind,
 attempt_id,phase_id,wire_d4,source_fingerprint,checkpoint_id,
 checkpoint_revision,checkpoint_digest,frame_digest,evaluation_sha256,
 artifact_sha256,rule_sha256,metric_states,computed_metric_keys,saved_at)
 VALUES(p_tenant_id,p_game_id,new_id,row_item.effective_event_id,
 row_item.effective_play_row_id,p.internal_generation,row_item.d1,row_item.d2,
 CASE WHEN row_item.d1=p.target_d1 THEN 2 ELSE old_source.slot_version END,
 CASE WHEN row_item.d1=p.target_d1 THEN 1 ELSE old_source.play_row_version END,
 CASE WHEN row_item.d1=p.target_d1 THEN 'past_correction'
 ELSE old_source.provider_kind END,
 CASE WHEN row_item.d1=p.target_d1 THEN p_attempt_id ELSE old_source.attempt_id END,
 CASE WHEN row_item.d1=p.target_d1 THEN p_phase_id ELSE old_source.phase_id END,
 CASE WHEN row_item.d1=p.target_d1 THEN binding.wire_d4 ELSE old_source.wire_d4 END,
 CASE WHEN row_item.d1=p.target_d1 THEN c->>'ledger_fingerprint'
 ELSE old_source.source_fingerprint END,
 CASE WHEN row_item.d1=p.target_d1 THEN (c->'next_checkpoint'->>'id')::uuid
 ELSE old_source.checkpoint_id END,
 CASE WHEN row_item.d1=p.target_d1 THEN
 (c->'next_checkpoint'->>'revision')::bigint
 ELSE old_source.checkpoint_revision END,
 CASE WHEN row_item.d1=p.target_d1 THEN c->'next_checkpoint'->>'content_digest'
 ELSE old_source.checkpoint_digest END,
 CASE WHEN row_item.d1=p.target_d1 THEN row_item.item_digest
 ELSE old_source.frame_digest END,
 pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(effective_eval::text,
 'UTF8')),'hex'),new_artifact,old_source.rule_sha256,effective_eval,source_keys,
 now_at);
 FOR metric IN SELECT key,value FROM pg_catalog.jsonb_each(
 effective_eval->'metrics') LOOP
 IF pg_catalog.jsonb_typeof(metric.value) IS DISTINCT FROM 'object'
 OR pg_catalog.jsonb_typeof(metric.value->'credits') IS DISTINCT FROM 'array'
 OR metric.value->>'state' NOT IN ('available','source_unavailable')
 THEN RAISE EXCEPTION 'P3 page finalize rejected' USING ERRCODE='42501'; END IF;
 IF metric.value->>'state'='available' THEN
 credit_ordinal:=0;
 FOR credit IN SELECT value FROM pg_catalog.jsonb_array_elements(
 metric.value->'credits') LOOP
 INSERT INTO sync_fence.stats_primitive_facts(
 tenant_id,game_id,fact_version_id,source_event_id,metric_id,player_id,
 credit_ordinal,state,amount)
 VALUES(p_tenant_id,p_game_id,new_id,row_item.effective_event_id,metric.key,
 (credit.value->>'player_id')::uuid,credit_ordinal,'available',
 (credit.value->>'quantity')::numeric);
 credit_ordinal:=credit_ordinal+1;
 END LOOP;
 ELSIF pg_catalog.jsonb_array_length(metric.value->'credits')<>0 THEN
 RAISE EXCEPTION 'P3 page finalize rejected' USING ERRCODE='42501'; END IF;
 END LOOP;
 END LOOP;
 UPDATE sync_fence.stats_fact_versions v SET computed_metric_keys=common_keys
 WHERE (v.tenant_id,v.game_id,v.id)=(p_tenant_id,p_game_id,new_id)
 AND v.is_current AND v.invalidated_at IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'P3 page finalize rejected'
 USING ERRCODE='42501'; END IF;
 SELECT count(*) INTO matched_count FROM sync_fence.stats_primitive_sources s
 WHERE (s.tenant_id,s.game_id,s.fact_version_id)=
 (p_tenant_id,p_game_id,new_id);
 IF matched_count IS DISTINCT FROM p.watermark
 THEN RAISE EXCEPTION 'P3 page finalize rejected' USING ERRCODE='42501'; END IF;
 UPDATE sync_fence.ordinary_pitch_checkpoints cp SET
 revision=(c->'next_checkpoint'->>'revision')::bigint,
 content_digest=c->'next_checkpoint'->>'content_digest',
 content=c->'next_checkpoint',saved_at=now_at
 WHERE (cp.tenant_id,cp.game_id,cp.internal_generation)=
 (p_tenant_id,p_game_id,p.internal_generation) AND cp.id=old_cp.id
 AND cp.revision=old_cp.revision AND cp.content_digest=old_cp.content_digest
 AND cp.content=old_cp.content AND cp.state='current';
 IF NOT FOUND THEN RAISE EXCEPTION 'P3 page finalize rejected'
 USING ERRCODE='42501'; END IF;
 IF game_status='finished' THEN
 UPDATE sync_fence.game_lifecycle_heads h SET active_stats_version_id=new_id
 WHERE (h.tenant_id,h.game_id,h.active_stats_version_id)=
 (p_tenant_id,p_game_id,old_stats.id)
 AND h.active_receipt_id=lifecycle.active_receipt_id AND h.is_finished;
 IF NOT FOUND THEN RAISE EXCEPTION 'P3 page finalize rejected'
 USING ERRCODE='42501'; END IF;
 END IF;
 UPDATE sync_fence.p3_projection_page_progress x SET
 state='finalized',finalized_at=now_at
 WHERE (x.tenant_id,x.game_id,x.internal_generation,x.capsule_id)=
 (p_tenant_id,p_game_id,p.internal_generation,p_capsule_id)
 AND x.state='building' AND x.item_count=x.watermark
 AND x.transaction_id=own_xid
 AND x.source_page_seal=p.source_page_seal
 AND x.evaluation_page_seal=p.evaluation_page_seal;
 IF NOT FOUND THEN RAISE EXCEPTION 'P3 page finalize rejected'
 USING ERRCODE='42501'; END IF;
 PERFORM sync_fence_api.assert_writer_binding(p_tenant_id,p_attempt_id,p_phase_id,
 p_binding_nonce,p_device_id,p_game_id);
 RETURN QUERY SELECT p_capsule_id,c->'next_checkpoint'->>'content_digest',
 evaluation_digest,new_id;
END;
$p3_page_finalize$;
ALTER FUNCTION sync_right_api.finalize_p3_projection_page(
 uuid,uuid,uuid,bytea,uuid,uuid,uuid)
 OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.finalize_p3_projection_page(
 uuid,uuid,uuid,bytea,uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_right_api.finalize_p3_projection_page(
 uuid,uuid,uuid,bytea,uuid,uuid,uuid) TO pitchlog_app;
