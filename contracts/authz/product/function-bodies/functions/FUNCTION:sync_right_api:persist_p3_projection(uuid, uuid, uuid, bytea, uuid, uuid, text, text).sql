-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:persist_p3_projection(uuid, uuid, uuid, bytea, uuid, uuid, text, text)

CREATE FUNCTION sync_right_api.persist_p3_projection(
p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding_nonce bytea,p_device_id uuid,p_game_id uuid,p_capsule_json text,p_stats_json text)
RETURNS TABLE(capsule_id uuid,checkpoint_digest text,evaluation_set_digest text,
 stats_version_id uuid) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_projection$
#variable_conflict use_variable
DECLARE tenant uuid; own_xid text; binding record;
 c jsonb; t jsonb; item jsonb; source_item jsonb;
 old_cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE;
 change_event public.operation_events%ROWTYPE;
 old_event public.operation_events%ROWTYPE;
 old_play public.play_rows%ROWTYPE;
 old_history sync_fence.ordinary_pitch_history%ROWTYPE;
 old_stats sync_fence.stats_fact_versions%ROWTYPE;
 old_source sync_fence.stats_primitive_sources%ROWTYPE;
 game_row record; lifecycle sync_fence.game_lifecycle_heads%ROWTYPE;
 health record; new_id uuid; new_event uuid; old_event_id uuid; new_play uuid;
 target_d1 bigint; generation bigint; watermark bigint; current_d1 bigint:=0;
 runner_rows jsonb; original_eval jsonb; effective_eval jsonb; new_artifact text;
 metric record; credit record; credit_ordinal bigint; source_keys text[];
 common_keys text[];
 now_at timestamptz; matched_count bigint;
BEGIN
 IF session_user<>'pitchlog_app' OR current_user<>'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_game_id IS NULL OR p_attempt_id IS NULL
 OR p_phase_id IS NULL OR p_device_id IS NULL OR p_binding_nonce IS NULL
 OR pg_catalog.octet_length(p_binding_nonce)<>32
 OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'off'
 OR p_capsule_json IS NULL OR p_stats_json IS NULL THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 PERFORM sync_fence_api.assert_writer_binding(p_tenant_id,p_attempt_id,p_phase_id,
 p_binding_nonce,p_device_id,p_game_id);
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 SELECT b.* INTO STRICT binding FROM sync_fence_api.read_p3_writer_binding(
 p_tenant_id,p_attempt_id,p_phase_id,p_binding_nonce,p_device_id,p_game_id) b;
 tenant:=binding.tenant_id;
 c:=p_capsule_json::jsonb; t:=p_stats_json::jsonb;
 IF pg_catalog.jsonb_typeof(c) IS DISTINCT FROM 'object'
 OR pg_catalog.jsonb_typeof(t) IS DISTINCT FROM 'object'
 OR c->>'version' IS DISTINCT FROM 'p3-current-capsule-v1'
 OR t->>'version' IS DISTINCT FROM 'p3-current-stats-v1'
 OR c->>'tenant_id' IS DISTINCT FROM tenant::text
 OR c->>'game_id' IS DISTINCT FROM p_game_id::text
 OR c->>'d5' IS DISTINCT FROM binding.d5::text
 OR c->>'ledger_fingerprint' !~ '^[a-f0-9]{64}$'
 OR t->>'capsule_id' IS DISTINCT FROM c->>'capsule_id'
 OR c->>'source_set_digest' !~ '^[a-f0-9]{64}$'
 OR t->>'evaluation_set_digest' !~ '^[a-f0-9]{64}$'
 OR t->>'model_sha256' IS DISTINCT FROM 'sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6'
 OR pg_catalog.jsonb_typeof(c->'items') IS DISTINCT FROM 'array'
 OR pg_catalog.jsonb_typeof(t->'sources') IS DISTINCT FROM 'array'
 OR pg_catalog.jsonb_array_length(c->'items') NOT BETWEEN 1 AND 25
 OR pg_catalog.jsonb_array_length(c->'items') IS DISTINCT FROM
 pg_catalog.jsonb_array_length(t->'sources') THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 generation:=(c->>'internal_generation')::bigint;
 target_d1:=(c->>'target_d1')::bigint;
 watermark:=pg_catalog.jsonb_array_length(c->'items');
 IF generation IS DISTINCT FROM binding.internal_generation
 OR target_d1 NOT BETWEEN 1 AND watermark
 OR (c->>'expected_version')::bigint<>1
 OR EXISTS(SELECT 1 FROM sync_fence.p3_projection_heads h
 WHERE (h.tenant_id,h.game_id,h.internal_generation)=(tenant,p_game_id,generation))
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 SELECT cp.* INTO STRICT old_cp FROM sync_fence.ordinary_pitch_checkpoints cp
 WHERE (cp.tenant_id,cp.game_id,cp.internal_generation)=(tenant,p_game_id,generation)
 AND cp.state='current' AND cp.confirmed_watermark=watermark
 AND cp.applied_watermark=watermark AND cp.id=(c->>'previous_checkpoint_id')::uuid
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
 OR target_d1>watermark
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 IF c->'next_checkpoint'->>'content_digest' !~ '^[a-f0-9]{64}$'
 OR c->'next_checkpoint'->'prefix_ref'->'checkpoint'->>'digest'
 !~ '^[a-f0-9]{64}$'
 OR (c->'next_checkpoint'->>'confirmed_watermark')::bigint<>watermark
 OR (c->'next_checkpoint'->>'applied_watermark')::bigint<>watermark
 OR (c->'next_checkpoint'->>'internal_generation')::bigint<>generation
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 SELECT e.* INTO STRICT change_event FROM public.operation_events e
 WHERE (e.tenant_id,e.game_id,e.id)=(tenant,p_game_id,(c->>'change_event_id')::uuid)
 AND e.event_kind='play_change' AND e.ledger_kind='accepted' AND NOT e.is_tombstone
 AND e.generation IS NULL AND e.d1 IS NULL AND e.d2 IS NULL
 AND e.target_generation=generation AND e.target_d1=target_d1
 AND e.expected_version=1 AND e.d5=binding.d5
 AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND NOT e.migration_unverified;
 IF NOT EXISTS(SELECT 1 FROM public.idempotency_ledger l
 WHERE l.tenant_id=tenant AND l.d5=binding.d5 AND l.kind='accepted'
 AND l.source_fingerprint=c->>'ledger_fingerprint' AND l.retired_at IS NULL)
 OR change_event.payload->>'formatVersion' IS DISTINCT FROM
 'p3-lineup-pitch-change-v1'
 OR change_event.payload->>'targetEventId' IS DISTINCT FROM
 c->'items'->((target_d1-1)::integer)->>'original_event_id'
 OR NOT EXISTS(SELECT 1 FROM public.event_slots slot
 WHERE (slot.tenant_id,slot.game_id,slot.generation,slot.d1)=
 (tenant,p_game_id,generation,target_d1) AND slot.confirmed_version=2)
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 SELECT v.* INTO STRICT old_stats FROM sync_fence.stats_fact_versions v
 WHERE (v.tenant_id,v.game_id,v.model_sha256)=(tenant,p_game_id,'sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6')
 AND v.is_current AND v.invalidated_at IS NULL
 AND v.source_count=watermark AND v.t5_artifact_set_sha256='b551ca128619674a5fc87efe44eba1acae329ed5979353600149dd4226e8dad2';
 SELECT g.status INTO STRICT game_row FROM public.games g
 WHERE (g.tenant_id,g.id)=(tenant,p_game_id) AND g.status IN ('in_progress','finished')
 AND g.hidden_at IS NULL AND g.trashed_at IS NULL
 AND g.import_batch_id IS NULL;
 IF (SELECT pg_catalog.count(*) FROM public.recording_generations r
 WHERE (r.tenant_id,r.game_id,r.generation)=(tenant,p_game_id,generation)
 AND r.kind='normal' AND r.holder_device=p_device_id::text
 AND r.revoked_at IS NULL AND r.retired_at IS NULL
 AND r.recovery_generation=(SELECT g.recovery_generation
 FROM public.rg1_restore_gate g WHERE g.singleton_id=1 AND g.state='open'))<>1
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 IF (game_row.status='finished') IS DISTINCT FROM
 (old_stats.completion_state='confirmed_ended')
 OR old_stats.rule_sha256 !~ '^[a-f0-9]{64}$'
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 IF game_row.status='finished' THEN
 SELECT h.* INTO STRICT lifecycle FROM sync_fence.game_lifecycle_heads h
 WHERE (h.tenant_id,h.game_id)=(tenant,p_game_id)
 AND h.is_finished AND h.active_stats_version_id=old_stats.id
 AND h.active_receipt_id=old_stats.completion_receipt_id
 AND h.active_receipt_id=old_stats.public_pointer_receipt_id FOR UPDATE;
 END IF;
 -- 旧版の全source・原event・履歴・物理行を元値と双方向照合する。
 FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(c->'items') LOOP
 current_d1:=current_d1+1;
 source_item:=t->'sources'->((current_d1-1)::integer);
 old_event_id:=(item->>'original_event_id')::uuid;
 new_event:=(item->>'effective_event_id')::uuid;
 new_play:=(item->>'effective_play_row_id')::uuid;
 original_eval:=source_item->'original_evaluation';
 effective_eval:=source_item->'evaluation';
 IF (item->>'d1')::bigint IS DISTINCT FROM current_d1
 OR (source_item->>'d1')::bigint IS DISTINCT FROM current_d1
 OR source_item->>'original_event_id' IS DISTINCT FROM old_event_id::text
 OR source_item->>'effective_event_id' IS DISTINCT FROM new_event::text
 OR source_item->>'effective_play_row_id' IS DISTINCT FROM new_play::text
 OR pg_catalog.jsonb_typeof(original_eval) IS DISTINCT FROM 'object'
 OR pg_catalog.jsonb_typeof(effective_eval) IS DISTINCT FROM 'object'
 OR original_eval->>'source_event_id' IS DISTINCT FROM old_event_id::text
 OR effective_eval->>'source_event_id' IS DISTINCT FROM new_event::text
 OR source_item->>'original_evaluation_digest' !~ '^[a-f0-9]{64}$'
 OR source_item->>'evaluation_digest' !~ '^[a-f0-9]{64}$'
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 SELECT e.* INTO STRICT old_event FROM public.operation_events e
 WHERE (e.tenant_id,e.game_id,e.id)=(tenant,p_game_id,old_event_id)
 AND e.event_kind='play_input' AND e.ledger_kind='accepted' AND NOT e.is_tombstone
 AND e.generation=generation AND e.d1=current_d1
 AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND NOT e.migration_unverified;
 SELECT p.* INTO STRICT old_play FROM public.play_rows p
 WHERE (p.tenant_id,p.game_id,p.id)=
 (tenant,p_game_id,(item->>'original_play_row_id')::uuid)
 AND p.source_event_id=old_event_id AND p.hidden_at IS NULL
 AND p.import_batch_id IS NULL AND NOT p.migration_unverified;
 SELECT h.* INTO STRICT old_history FROM sync_fence.ordinary_pitch_history h
 WHERE (h.tenant_id,h.game_id,h.internal_generation,h.source_event_id,h.d1)=
 (tenant,p_game_id,generation,old_event_id,current_d1)
 AND h.history_version=old_cp.history_version;
 SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(r)
 ORDER BY r.base),'[]'::jsonb)
 INTO runner_rows FROM public.play_runners r WHERE r.tenant_id=tenant
 AND r.play_id=old_play.id;
 SELECT s.* INTO STRICT old_source FROM sync_fence.stats_primitive_sources s
 WHERE (s.tenant_id,s.game_id,s.fact_version_id,s.source_event_id)=
 (tenant,p_game_id,old_stats.id,old_event_id)
 AND s.recording_generation=generation AND s.d1=current_d1;
 IF item->'original_payload' IS DISTINCT FROM old_event.payload
 OR item->'original_history_entry' IS DISTINCT FROM old_history.entry
 OR item->'original_play_row' IS DISTINCT FROM pg_catalog.to_jsonb(old_play)
 OR item->'original_play_runners' IS DISTINCT FROM runner_rows
 OR original_eval IS DISTINCT FROM old_source.metric_states
 OR original_eval->>'native_rule_sha256' IS DISTINCT FROM old_source.rule_sha256
 OR old_source.play_row_id IS DISTINCT FROM old_play.id
 OR old_source.d2 IS DISTINCT FROM old_event.d2
 OR item->>'d2' IS DISTINCT FROM old_event.d2::text
 OR item->>'original_play_row_id' IS DISTINCT FROM old_play.id::text
 OR item->>'original_event_id' IS DISTINCT FROM old_event.id::text
 OR old_source.evaluation_sha256 IS DISTINCT FROM pg_catalog.encode(
 pg_catalog.sha256(pg_catalog.convert_to(original_eval::text,'UTF8')),'hex')
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 IF current_d1=target_d1 THEN
   IF new_event IS DISTINCT FROM change_event.id OR new_play=old_play.id
   OR item->>'state' IS DISTINCT FROM 'corrected'
   OR item->'play_row'->>'source_event_id' IS DISTINCT FROM new_event::text
   OR item->'play_row'->>'id' IS DISTINCT FROM new_play::text
   THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 ELSE
   IF new_event IS DISTINCT FROM old_event.id OR new_play IS DISTINCT FROM old_play.id
   OR item->'play_row' IS DISTINCT FROM pg_catalog.to_jsonb(old_play)
   OR item->'play_runners' IS DISTINCT FROM runner_rows
   THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 END IF;
 END LOOP;
 -- 元全値を閉じた後だけP3有効対象行を追記する。元行は物理削除しない。
 item:=c->'items'->((target_d1-1)::integer);
 INSERT INTO sync_fence.p3_projection_write_admissions(
 tenant_id,attempt_id,phase_id,game_id,internal_generation,capsule_id,
 change_event_id,play_row_id,ledger_fingerprint,expected_play_row,transaction_id,state)
 VALUES(tenant,p_attempt_id,p_phase_id,p_game_id,generation,
 (c->>'capsule_id')::uuid,change_event.id,
 (item->>'effective_play_row_id')::uuid,c->>'ledger_fingerprint',
 item->'play_row',own_xid,'ready');
 IF pg_catalog.jsonb_array_length(item->'play_runners')<>0 THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 IF item->'play_row'->'hidden_at' IS DISTINCT FROM 'null'::jsonb
 OR item->'play_row'->'import_batch_id' IS DISTINCT FROM 'null'::jsonb
 OR item->'play_row'->'legacy_row_identifier' IS DISTINCT FROM 'null'::jsonb
 OR item->'play_row'->'migration_unverified' IS DISTINCT FROM 'false'::jsonb THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 INSERT INTO public.play_rows (batted_ball_strength,batted_ball_type,batter_id,batter_status,batting_order,batting_result_key,batting_side,catcher_id,comment,course_x,course_y,error_type,event_kind,fake_run,game_id,hit_x,hit_y,id,pickoff_detail,pickoff_type,pitch_speed,pitch_type_key,pitcher_id,play_number,press,raw_error_position,raw_fielder_position,resolved_error_player_id,resolved_fielder_id,secondary_batting_result_key,source_event_id,stance,strategy_detail_key,strategy_key,strategy_result_key,tenant_id,version)
 SELECT r.batted_ball_strength,r.batted_ball_type,r.batter_id,r.batter_status,r.batting_order,r.batting_result_key,r.batting_side,r.catcher_id,r.comment,r.course_x,r.course_y,r.error_type,r.event_kind,r.fake_run,r.game_id,r.hit_x,r.hit_y,r.id,r.pickoff_detail,r.pickoff_type,r.pitch_speed,r.pitch_type_key,r.pitcher_id,r.play_number,r.press,r.raw_error_position,r.raw_fielder_position,r.resolved_error_player_id,r.resolved_fielder_id,r.secondary_batting_result_key,r.source_event_id,r.stance,r.strategy_detail_key,r.strategy_key,r.strategy_result_key,r.tenant_id,r.version FROM pg_catalog.jsonb_populate_record(
 NULL::public.play_rows,item->'play_row') r;
 IF NOT EXISTS(SELECT 1 FROM sync_fence.p3_projection_write_admissions a
 WHERE (a.tenant_id,a.attempt_id,a.phase_id)=(tenant,p_attempt_id,p_phase_id)
 AND a.state='consumed' AND a.transaction_id=own_xid) THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 new_id:=pg_catalog.gen_random_uuid(); now_at:=pg_catalog.clock_timestamp();
 INSERT INTO sync_fence.p3_projection_capsules(
 tenant_id,game_id,internal_generation,id,change_event_id,d5,target_d1,expected_version,
 prior_checkpoint_id,prior_checkpoint_revision,prior_checkpoint_digest,
 prior_checkpoint_content,
 next_checkpoint_id,next_checkpoint_revision,next_checkpoint_digest,
 next_checkpoint_content,source_set_digest,stats_evaluation_set_digest,
 stats_model_sha256,stats_version_id,watermark,created_at)
 VALUES(tenant,p_game_id,generation,(c->>'capsule_id')::uuid,change_event.id,binding.d5,
 target_d1,1,old_cp.id,old_cp.revision,old_cp.content_digest,old_cp.content,
 (c->'next_checkpoint'->>'id')::uuid,(c->'next_checkpoint'->>'revision')::bigint,
 c->'next_checkpoint'->>'content_digest',c->'next_checkpoint',
 c->>'source_set_digest',t->>'evaluation_set_digest','sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6',new_id,watermark,now_at);
 INSERT INTO sync_fence.p3_projection_capsule_items(
 tenant_id,game_id,internal_generation,capsule_id,d1,d2,state,
 original_event_id,effective_event_id,original_play_row_id,effective_play_row_id,
 original_payload,original_history_entry,original_play_row,original_play_runners,
 payload,history_entry,play_row,play_runners,item_digest)
 SELECT tenant,p_game_id,generation,(c->>'capsule_id')::uuid,
 (j.value->>'d1')::bigint,(j.value->>'d2')::bigint,j.value->>'state',
 (j.value->>'original_event_id')::uuid,(j.value->>'effective_event_id')::uuid,
 (j.value->>'original_play_row_id')::uuid,(j.value->>'effective_play_row_id')::uuid,
 j.value->'original_payload',j.value->'original_history_entry',
 j.value->'original_play_row',j.value->'original_play_runners',
 j.value->'payload',j.value->'history_entry',j.value->'play_row',
 j.value->'play_runners',j.value->>'digest'
 FROM pg_catalog.jsonb_array_elements(c->'items') j;
 INSERT INTO sync_fence.p3_projection_heads(tenant_id,game_id,internal_generation,
 capsule_id,revision,source_set_digest,stats_version_id,updated_at)
 VALUES(tenant,p_game_id,generation,(c->>'capsule_id')::uuid,1,
 c->>'source_set_digest',new_id,now_at);
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
 OR health.canonical_source_count IS DISTINCT FROM watermark
 OR health.canonical_source_set_sha256 !~ '^[a-f0-9]{64}$'
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 UPDATE sync_fence.stats_fact_versions v SET is_current=false,invalidated_at=now_at
 WHERE (v.tenant_id,v.game_id,v.id)=(tenant,p_game_id,old_stats.id)
 AND v.is_current AND v.invalidated_at IS NULL;
 IF NOT FOUND THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 INSERT INTO sync_fence.stats_fact_versions(
 tenant_id,game_id,id,model_sha256,rule_sha256,t5_artifact_set_sha256,
 source_set_sha256,source_count,revision,last_generation,last_d1,last_d2,
 updated_at,computed_metric_keys,is_current,completion_state,
 completion_receipt_id,public_pointer_receipt_id,created_at,invalidated_at)
 SELECT tenant,p_game_id,new_id,v.model_sha256,v.rule_sha256,v.t5_artifact_set_sha256,
 health.canonical_source_set_sha256,watermark,v.revision+1,
 v.last_generation,v.last_d1,v.last_d2,now_at,v.computed_metric_keys,true,
 v.completion_state,v.completion_receipt_id,v.public_pointer_receipt_id,now_at,NULL
 FROM sync_fence.stats_fact_versions v WHERE (v.tenant_id,v.game_id,v.id)=
 (tenant,p_game_id,old_stats.id);
 FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(c->'items') LOOP
 current_d1:=(item->>'d1')::bigint;
 source_item:=t->'sources'->((current_d1-1)::integer);
 old_event_id:=(item->>'original_event_id')::uuid;
 new_event:=(item->>'effective_event_id')::uuid;
 new_play:=(item->>'effective_play_row_id')::uuid;
 effective_eval:=source_item->'evaluation';
 IF pg_catalog.jsonb_typeof(effective_eval->'metrics') IS DISTINCT FROM 'object'
 OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
 pg_catalog.jsonb_object_keys(effective_eval) k) IS DISTINCT FROM
 ARRAY['decisions','metrics','native_rule_sha256','pa_row','selected','source_event_id']::text[]
 OR effective_eval->>'native_rule_sha256' IS DISTINCT FROM old_source.rule_sha256
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 SELECT s.* INTO STRICT old_source FROM sync_fence.stats_primitive_sources s
 WHERE (s.tenant_id,s.game_id,s.fact_version_id,s.source_event_id)=
 (tenant,p_game_id,old_stats.id,old_event_id);
 new_artifact:=item->'payload'->'calculation'->>'artifactSha256';
 IF new_artifact IS NULL OR new_artifact !~ '^[a-f0-9]{64}$'
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 SELECT COALESCE(pg_catalog.array_agg(key ORDER BY key),'{}'::text[])
 INTO source_keys FROM pg_catalog.jsonb_each(effective_eval->'metrics')
 WHERE value->>'state'='available';
 IF current_d1=1 THEN common_keys:=source_keys;
 ELSE
 common_keys:=ARRAY(SELECT k FROM pg_catalog.unnest(common_keys) k
 WHERE k=ANY(source_keys) ORDER BY k);
 END IF;
 INSERT INTO sync_fence.stats_primitive_sources(
 tenant_id,game_id,fact_version_id,source_event_id,play_row_id,
 recording_generation,d1,d2,slot_version,play_row_version,provider_kind,
 attempt_id,phase_id,wire_d4,source_fingerprint,checkpoint_id,
 checkpoint_revision,checkpoint_digest,frame_digest,evaluation_sha256,
 artifact_sha256,rule_sha256,metric_states,computed_metric_keys,saved_at)
 VALUES(tenant,p_game_id,new_id,new_event,new_play,generation,current_d1,
 old_source.d2,CASE WHEN current_d1=target_d1 THEN 2 ELSE old_source.slot_version END,
 CASE WHEN current_d1=target_d1 THEN 1 ELSE old_source.play_row_version END,
 CASE WHEN current_d1=target_d1 THEN 'past_correction'
 ELSE old_source.provider_kind END,
 CASE WHEN current_d1=target_d1 THEN p_attempt_id ELSE old_source.attempt_id END,
 CASE WHEN current_d1=target_d1 THEN p_phase_id ELSE old_source.phase_id END,
 CASE WHEN current_d1=target_d1 THEN binding.wire_d4 ELSE old_source.wire_d4 END,
 CASE WHEN current_d1=target_d1 THEN c->>'ledger_fingerprint'
 ELSE old_source.source_fingerprint END,
 CASE WHEN current_d1=target_d1 THEN (c->'next_checkpoint'->>'id')::uuid
 ELSE old_source.checkpoint_id END,
 CASE WHEN current_d1=target_d1 THEN (c->'next_checkpoint'->>'revision')::bigint
 ELSE old_source.checkpoint_revision END,
 CASE WHEN current_d1=target_d1 THEN c->'next_checkpoint'->>'content_digest'
 ELSE old_source.checkpoint_digest END,
 CASE WHEN current_d1=target_d1 THEN item->>'digest' ELSE old_source.frame_digest END,
 pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(effective_eval::text,'UTF8')),'hex'),
 new_artifact,old_source.rule_sha256,effective_eval,source_keys,now_at);
 FOR metric IN SELECT key,value FROM
 pg_catalog.jsonb_each(effective_eval->'metrics') LOOP
 IF pg_catalog.jsonb_typeof(metric.value) IS DISTINCT FROM 'object'
 OR pg_catalog.jsonb_typeof(metric.value->'credits') IS DISTINCT FROM 'array'
 OR metric.value->>'state' NOT IN ('available','source_unavailable')
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 IF metric.value->>'state'='available' THEN
 credit_ordinal:=0;
 FOR credit IN SELECT value FROM pg_catalog.jsonb_array_elements(
 metric.value->'credits') LOOP
 INSERT INTO sync_fence.stats_primitive_facts(
 tenant_id,game_id,fact_version_id,source_event_id,metric_id,player_id,
 credit_ordinal,state,amount)
 VALUES(tenant,p_game_id,new_id,new_event,metric.key,
 (credit.value->>'player_id')::uuid,credit_ordinal,'available',
 (credit.value->>'quantity')::numeric);
 credit_ordinal:=credit_ordinal+1;
 END LOOP;
 ELSIF pg_catalog.jsonb_array_length(metric.value->'credits')<>0 THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501';
 END IF;
 END LOOP;
 END LOOP;
 UPDATE sync_fence.stats_fact_versions v SET computed_metric_keys=common_keys
 WHERE (v.tenant_id,v.game_id,v.id)=(tenant,p_game_id,new_id)
 AND v.is_current AND v.invalidated_at IS NULL;
 IF NOT FOUND THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 SELECT count(*) INTO matched_count FROM sync_fence.stats_primitive_sources s
 WHERE (s.tenant_id,s.game_id,s.fact_version_id)=(tenant,p_game_id,new_id);
 IF matched_count<>watermark THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 UPDATE sync_fence.ordinary_pitch_checkpoints cp SET
 revision=(c->'next_checkpoint'->>'revision')::bigint,
 content_digest=c->'next_checkpoint'->>'content_digest',
 content=c->'next_checkpoint',saved_at=now_at
 WHERE (cp.tenant_id,cp.game_id,cp.internal_generation)=
 (tenant,p_game_id,generation) AND cp.id=old_cp.id
 AND cp.revision=old_cp.revision AND cp.content_digest=old_cp.content_digest
 AND cp.content=old_cp.content AND cp.state='current';
 IF NOT FOUND THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 IF game_row.status='finished' THEN
 UPDATE sync_fence.game_lifecycle_heads h SET active_stats_version_id=new_id
 WHERE (h.tenant_id,h.game_id,h.active_stats_version_id)=
 (tenant,p_game_id,old_stats.id) AND h.active_receipt_id=lifecycle.active_receipt_id
 AND h.is_finished;
 IF NOT FOUND THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 END IF;
 PERFORM sync_fence_api.assert_writer_binding(p_tenant_id,p_attempt_id,p_phase_id,
 p_binding_nonce,p_device_id,p_game_id);
 RETURN QUERY SELECT (c->>'capsule_id')::uuid,
 c->'next_checkpoint'->>'content_digest',t->>'evaluation_set_digest',new_id;
END;
$p3_projection$;
ALTER FUNCTION sync_right_api.persist_p3_projection(
 uuid,uuid,uuid,bytea,uuid,uuid,text,text)
 OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.persist_p3_projection(
 uuid,uuid,uuid,bytea,uuid,uuid,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_right_api.persist_p3_projection(
 uuid,uuid,uuid,bytea,uuid,uuid,text,text) TO pitchlog_app;
