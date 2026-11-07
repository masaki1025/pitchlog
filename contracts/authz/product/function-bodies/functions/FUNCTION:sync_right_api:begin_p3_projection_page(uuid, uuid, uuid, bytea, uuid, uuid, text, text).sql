-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:begin_p3_projection_page(uuid, uuid, uuid, bytea, uuid, uuid, text, text)

CREATE FUNCTION sync_right_api.begin_p3_projection_page(
p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding_nonce bytea,p_device_id uuid,p_game_id uuid,p_capsule_header text,p_stats_header text)
RETURNS TABLE(capsule_id uuid,watermark bigint) LANGUAGE plpgsql VOLATILE
SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $p3_page_begin$
#variable_conflict use_variable
DECLARE binding record; c jsonb; t jsonb; own_xid text;
 generation bigint; target_d1 bigint; expected_watermark bigint;
 old_cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE;
 old_stats sync_fence.stats_fact_versions%ROWTYPE;
 change_event public.operation_events%ROWTYPE;
 game_row public.games%ROWTYPE;
 lifecycle sync_fence.game_lifecycle_heads%ROWTYPE;
 source_keys text[]; stats_keys text[];
 now_at timestamptz;
BEGIN
 IF session_user<>'pitchlog_app' OR current_user<>'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_attempt_id IS NULL OR p_phase_id IS NULL
 OR p_device_id IS NULL OR p_game_id IS NULL OR p_binding_nonce IS NULL
 OR pg_catalog.octet_length(p_binding_nonce)<>32
 OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'off'
 OR p_capsule_header IS NULL OR p_stats_header IS NULL THEN
 RAISE EXCEPTION 'P3 page begin rejected' USING ERRCODE='42501'; END IF;
 PERFORM sync_fence_api.assert_writer_binding(p_tenant_id,p_attempt_id,p_phase_id,
 p_binding_nonce,p_device_id,p_game_id);
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 SELECT b.* INTO STRICT binding FROM sync_fence_api.read_p3_writer_binding(
 p_tenant_id,p_attempt_id,p_phase_id,p_binding_nonce,p_device_id,p_game_id) b;
 c:=p_capsule_header::jsonb; t:=p_stats_header::jsonb;
 IF pg_catalog.jsonb_typeof(c) IS DISTINCT FROM 'object'
 OR pg_catalog.jsonb_typeof(t) IS DISTINCT FROM 'object'
 OR c->>'version' IS DISTINCT FROM 'p3-current-capsule-page-v2'
 OR t->>'version' IS DISTINCT FROM 'p3-current-stats-page-v2'
 OR c->>'digest_format' IS DISTINCT FROM 'p3-page-chain-v2'
 OR c->>'tenant_id' IS DISTINCT FROM p_tenant_id::text
 OR c->>'game_id' IS DISTINCT FROM p_game_id::text
 OR c->>'d5' IS DISTINCT FROM binding.d5::text
 OR c->>'ledger_fingerprint' !~ '^[a-f0-9]{64}$'
 OR c->>'source_set_digest' !~ '^[a-f0-9]{64}$'
 OR c->>'item_chain' !~ '^[a-f0-9]{64}$'
 OR c->>'page_seal' !~ '^[a-f0-9]{64}$'
 OR t->>'evaluation_set_digest' !~ '^[a-f0-9]{64}$'
 OR t->>'evaluation_chain' !~ '^[a-f0-9]{64}$'
 OR t->>'model_sha256' IS DISTINCT FROM 'sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6'
 OR t->>'capsule_id' IS DISTINCT FROM c->>'capsule_id'
 OR c ? 'items' OR t ? 'sources'
 THEN RAISE EXCEPTION 'P3 page begin rejected' USING ERRCODE='42501'; END IF;
 SELECT pg_catalog.array_agg(k ORDER BY k) INTO STRICT source_keys
 FROM pg_catalog.jsonb_object_keys(c) k;
 IF source_keys IS DISTINCT FROM ARRAY[
 'capsule_id','change_event_id','d5','digest_format','game_id',
 'internal_generation','item_chain','ledger_fingerprint','next_checkpoint',
 'page_seal','previous_checkpoint','previous_checkpoint_digest',
 'previous_checkpoint_id','previous_checkpoint_revision',
 'source_set_digest','target_d1','tenant_id','version','watermark']::text[]
 THEN RAISE EXCEPTION 'P3 page begin rejected' USING ERRCODE='42501'; END IF;
 SELECT pg_catalog.array_agg(k ORDER BY k) INTO STRICT stats_keys
 FROM pg_catalog.jsonb_object_keys(t) k;
 IF stats_keys IS DISTINCT FROM ARRAY[
 'capsule_id','evaluation_chain','evaluation_set_digest','model_sha256','version']::text[]
 THEN RAISE EXCEPTION 'P3 page begin rejected' USING ERRCODE='42501'; END IF;
 generation:=(c->>'internal_generation')::bigint;
 target_d1:=(c->>'target_d1')::bigint;
 expected_watermark:=(c->>'watermark')::bigint;
 IF generation IS DISTINCT FROM binding.internal_generation
 OR expected_watermark<=25 OR target_d1 NOT BETWEEN 1 AND expected_watermark
 OR EXISTS(SELECT 1 FROM sync_fence.p3_projection_heads h
 WHERE (h.tenant_id,h.game_id,h.internal_generation)=
 (p_tenant_id,p_game_id,generation))
 OR EXISTS(SELECT 1 FROM sync_fence.p3_projection_page_progress p
 WHERE (p.tenant_id,p.game_id,p.internal_generation)=
 (p_tenant_id,p_game_id,generation))
 THEN RAISE EXCEPTION 'P3 page begin rejected' USING ERRCODE='42501'; END IF;
 SELECT cp.* INTO STRICT old_cp FROM sync_fence.ordinary_pitch_checkpoints cp
 WHERE (cp.tenant_id,cp.game_id,cp.internal_generation)=
 (p_tenant_id,p_game_id,generation) AND cp.state='current'
 AND cp.confirmed_watermark=expected_watermark
 AND cp.applied_watermark=expected_watermark
 AND cp.id=(c->>'previous_checkpoint_id')::uuid
 AND cp.revision=(c->>'previous_checkpoint_revision')::bigint
 AND cp.content_digest=c->>'previous_checkpoint_digest' FOR UPDATE;
 IF old_cp.content IS DISTINCT FROM c->'previous_checkpoint'
 OR (c->'next_checkpoint'->>'id')::uuid IS DISTINCT FROM old_cp.id
 OR (c->'next_checkpoint'->>'history_version')::bigint IS DISTINCT FROM
 old_cp.history_version
 OR c->'next_checkpoint'->'storage_anchor' IS DISTINCT FROM
 old_cp.content->'storage_anchor'
 OR c->'next_checkpoint'->>'wire_d4' IS DISTINCT FROM
 old_cp.content->>'wire_d4'
 OR c->'next_checkpoint'->>'content_digest' !~ '^[a-f0-9]{64}$'
 OR c->'next_checkpoint'->'prefix_ref'->'checkpoint'->>'digest'
 !~ '^[a-f0-9]{64}$'
 OR (c->'next_checkpoint'->>'confirmed_watermark')::bigint IS DISTINCT FROM
 expected_watermark
 OR (c->'next_checkpoint'->>'applied_watermark')::bigint IS DISTINCT FROM
 expected_watermark
 OR (c->'next_checkpoint'->>'internal_generation')::bigint IS DISTINCT FROM
 generation
 THEN RAISE EXCEPTION 'P3 page begin rejected' USING ERRCODE='42501'; END IF;
 SELECT e.* INTO STRICT change_event FROM public.operation_events e
 WHERE (e.tenant_id,e.game_id,e.id)=
 (p_tenant_id,p_game_id,(c->>'change_event_id')::uuid)
 AND e.event_kind='play_change' AND e.ledger_kind='accepted' AND NOT e.is_tombstone
 AND e.generation IS NULL AND e.d1 IS NULL AND e.d2 IS NULL
 AND e.target_generation=generation AND e.target_d1=target_d1
 AND e.expected_version=1 AND e.d5=binding.d5
 AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND NOT e.migration_unverified;
 IF NOT EXISTS(SELECT 1 FROM public.idempotency_ledger l
 WHERE l.tenant_id=p_tenant_id AND l.d5=binding.d5 AND l.kind='accepted'
 AND l.source_fingerprint=c->>'ledger_fingerprint' AND l.retired_at IS NULL)
 OR change_event.payload->>'formatVersion' IS DISTINCT FROM
 'p3-lineup-pitch-change-v1'
 OR NOT EXISTS(SELECT 1 FROM public.event_slots slot
 WHERE (slot.tenant_id,slot.game_id,slot.generation,slot.d1)=
 (p_tenant_id,p_game_id,generation,target_d1) AND slot.confirmed_version=2)
 THEN RAISE EXCEPTION 'P3 page begin rejected' USING ERRCODE='42501'; END IF;
 SELECT v.* INTO STRICT old_stats FROM sync_fence.stats_fact_versions v
 WHERE (v.tenant_id,v.game_id,v.model_sha256)=
 (p_tenant_id,p_game_id,'sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6')
 AND v.is_current AND v.invalidated_at IS NULL
 AND v.source_count=expected_watermark
 AND v.t5_artifact_set_sha256='b551ca128619674a5fc87efe44eba1acae329ed5979353600149dd4226e8dad2' FOR UPDATE;
 SELECT g.* INTO STRICT game_row FROM public.games g
 WHERE (g.tenant_id,g.id)=(p_tenant_id,p_game_id)
 AND g.status IN ('in_progress','finished') AND g.hidden_at IS NULL
 AND g.trashed_at IS NULL AND g.import_batch_id IS NULL;
 IF (SELECT pg_catalog.count(*) FROM public.recording_generations r
 WHERE (r.tenant_id,r.game_id,r.generation)=
 (p_tenant_id,p_game_id,generation) AND r.kind='normal'
 AND r.holder_device=p_device_id::text AND r.revoked_at IS NULL
 AND r.retired_at IS NULL AND r.recovery_generation=(SELECT gate.recovery_generation
 FROM public.rg1_restore_gate gate WHERE gate.singleton_id=1 AND gate.state='open'))<>1
 OR (game_row.status='finished') IS DISTINCT FROM
 (old_stats.completion_state='confirmed_ended')
 OR old_stats.rule_sha256 !~ '^[a-f0-9]{64}$'
 THEN RAISE EXCEPTION 'P3 page begin rejected' USING ERRCODE='42501'; END IF;
 IF game_row.status='finished' THEN
 SELECT h.* INTO STRICT lifecycle FROM sync_fence.game_lifecycle_heads h
 WHERE (h.tenant_id,h.game_id)=(p_tenant_id,p_game_id)
 AND h.is_finished AND h.active_stats_version_id=old_stats.id
 AND h.active_receipt_id=old_stats.completion_receipt_id
 AND h.active_receipt_id=old_stats.public_pointer_receipt_id FOR UPDATE;
 END IF;
 now_at:=pg_catalog.clock_timestamp();
 INSERT INTO sync_fence.p3_projection_page_progress(
 tenant_id,game_id,internal_generation,capsule_id,attempt_id,phase_id,
 device_id,binding_nonce,transaction_id,watermark,digest_format,target_d1,d5,
 old_stats_version_id,capsule_header,stats_header,state,item_count,last_d1,
 last_d2,page_count,source_page_seal,evaluation_page_seal,created_at,finalized_at)
 VALUES(p_tenant_id,p_game_id,generation,(c->>'capsule_id')::uuid,p_attempt_id,
 p_phase_id,p_device_id,p_binding_nonce,own_xid,expected_watermark,
 'p3-page-chain-v2',target_d1,binding.d5,old_stats.id,c,t,'building',
 0,0,0,0,repeat('0',64),repeat('0',64),now_at,NULL);
 PERFORM sync_fence_api.assert_writer_binding(p_tenant_id,p_attempt_id,p_phase_id,
 p_binding_nonce,p_device_id,p_game_id);
 RETURN QUERY SELECT (c->>'capsule_id')::uuid,expected_watermark;
END;
$p3_page_begin$;
ALTER FUNCTION sync_right_api.begin_p3_projection_page(
 uuid,uuid,uuid,bytea,uuid,uuid,text,text)
 OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.begin_p3_projection_page(
 uuid,uuid,uuid,bytea,uuid,uuid,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_right_api.begin_p3_projection_page(
 uuid,uuid,uuid,bytea,uuid,uuid,text,text) TO pitchlog_app;
