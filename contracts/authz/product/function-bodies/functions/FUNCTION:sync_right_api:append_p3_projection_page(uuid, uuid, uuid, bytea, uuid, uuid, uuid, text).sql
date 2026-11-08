-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:append_p3_projection_page(uuid, uuid, uuid, bytea, uuid, uuid, uuid, text)

CREATE FUNCTION sync_right_api.append_p3_projection_page(
p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding_nonce bytea,p_device_id uuid,p_game_id uuid,p_capsule_id uuid,p_page_json text)
RETURNS TABLE(last_d1 bigint,source_chain text,evaluation_chain text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_page_append$
#variable_conflict use_variable
DECLARE binding record; progress sync_fence.p3_projection_page_progress%ROWTYPE;
 c jsonb; page jsonb; source_item jsonb; item jsonb; member jsonb;
 old_cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE;
 old_stats sync_fence.stats_fact_versions%ROWTYPE;
 old_event public.operation_events%ROWTYPE;
 old_play public.play_rows%ROWTYPE;
 old_history sync_fence.ordinary_pitch_history%ROWTYPE;
 old_source sync_fence.stats_primitive_sources%ROWTYPE;
 change_event public.operation_events%ROWTYPE;
 old_event_id uuid; new_event_id uuid; new_play_id uuid;
 now_at timestamptz; own_xid text; d1 bigint; d2 bigint;
 prior_d2 bigint; row_count bigint:=0; old_runners jsonb;
 original_eval jsonb; effective_eval jsonb;
 source_hash text; evaluation_hash text; item_digest text;
BEGIN
 IF session_user<>'pitchlog_app' OR current_user<>'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_attempt_id IS NULL OR p_phase_id IS NULL
 OR p_device_id IS NULL OR p_game_id IS NULL OR p_capsule_id IS NULL
 OR p_binding_nonce IS NULL OR pg_catalog.octet_length(p_binding_nonce)<>32
 OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'off'
 OR p_page_json IS NULL THEN
 RAISE EXCEPTION 'P3 page append rejected' USING ERRCODE='42501'; END IF;
 PERFORM sync_fence_api.assert_writer_binding(p_tenant_id,p_attempt_id,p_phase_id,
 p_binding_nonce,p_device_id,p_game_id);
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 SELECT b.* INTO STRICT binding FROM sync_fence_api.read_p3_writer_binding(
 p_tenant_id,p_attempt_id,p_phase_id,p_binding_nonce,p_device_id,p_game_id) b;
 SELECT p.* INTO STRICT progress FROM sync_fence.p3_projection_page_progress p
 WHERE (p.tenant_id,p.game_id,p.internal_generation,p.capsule_id)=
 (p_tenant_id,p_game_id,binding.internal_generation,p_capsule_id)
 AND (p.attempt_id,p.phase_id,p.device_id,p.binding_nonce,p.transaction_id)=
 (p_attempt_id,p_phase_id,p_device_id,p_binding_nonce,own_xid)
 AND p.d5=binding.d5 AND p.state='building' AND p.item_count<p.watermark
 FOR UPDATE;
 c:=progress.capsule_header;
 page:=p_page_json::jsonb;
 IF pg_catalog.jsonb_typeof(page) IS DISTINCT FROM 'array'
 OR pg_catalog.jsonb_array_length(page) NOT BETWEEN 1 AND 25
 OR pg_catalog.jsonb_array_length(page)>progress.watermark-progress.item_count
 OR c->>'digest_format' IS DISTINCT FROM progress.digest_format
 THEN RAISE EXCEPTION 'P3 page append rejected' USING ERRCODE='42501'; END IF;
 SELECT cp.* INTO STRICT old_cp FROM sync_fence.ordinary_pitch_checkpoints cp
 WHERE (cp.tenant_id,cp.game_id,cp.internal_generation)=
 (p_tenant_id,p_game_id,progress.internal_generation)
 AND cp.id=(c->>'previous_checkpoint_id')::uuid
 AND cp.revision=(c->>'previous_checkpoint_revision')::bigint
 AND cp.content_digest=c->>'previous_checkpoint_digest'
 AND cp.content=c->'previous_checkpoint' AND cp.state='current'
 AND cp.confirmed_watermark=progress.watermark
 AND cp.applied_watermark=progress.watermark FOR SHARE;
 SELECT v.* INTO STRICT old_stats FROM sync_fence.stats_fact_versions v
 WHERE (v.tenant_id,v.game_id,v.id)=
 (p_tenant_id,p_game_id,progress.old_stats_version_id)
 AND v.is_current AND v.invalidated_at IS NULL
 AND v.source_count=progress.watermark FOR SHARE;
 SELECT e.* INTO STRICT change_event FROM public.operation_events e
 WHERE (e.tenant_id,e.game_id,e.id)=
 (p_tenant_id,p_game_id,(c->>'change_event_id')::uuid)
 AND e.event_kind='play_change' AND e.ledger_kind='accepted'
 AND NOT e.is_tombstone AND e.d5=binding.d5
 AND e.target_generation=progress.internal_generation
 AND e.target_d1=progress.target_d1
 AND e.expected_version=1 AND e.replaced_at IS NULL AND e.retired_at IS NULL;
 IF (SELECT pg_catalog.count(*) FROM public.recording_generations r
 WHERE (r.tenant_id,r.game_id,r.generation)=
 (p_tenant_id,p_game_id,progress.internal_generation)
 AND r.kind='normal' AND r.holder_device=p_device_id::text
 AND r.revoked_at IS NULL AND r.retired_at IS NULL
 AND r.recovery_generation=(SELECT gate.recovery_generation
 FROM public.rg1_restore_gate gate WHERE gate.singleton_id=1 AND gate.state='open'))<>1
 THEN RAISE EXCEPTION 'P3 page append rejected' USING ERRCODE='42501'; END IF;
 source_hash:=progress.source_page_seal;
 evaluation_hash:=progress.evaluation_page_seal;
 prior_d2:=progress.last_d2;
 now_at:=pg_catalog.clock_timestamp();
 FOR member IN SELECT value FROM pg_catalog.jsonb_array_elements(page) LOOP
 row_count:=row_count+1;
 IF pg_catalog.jsonb_typeof(member) IS DISTINCT FROM 'object'
 OR member ? 'item' IS FALSE OR member ? 'source' IS FALSE
 OR (SELECT pg_catalog.array_agg(k ORDER BY k)
 FROM pg_catalog.jsonb_object_keys(member) k)
 IS DISTINCT FROM ARRAY['item','source']::text[]
 THEN RAISE EXCEPTION 'P3 page append rejected' USING ERRCODE='42501'; END IF;
 item:=member->'item'; source_item:=member->'source';
 IF pg_catalog.jsonb_typeof(item) IS DISTINCT FROM 'object'
 OR pg_catalog.jsonb_typeof(source_item) IS DISTINCT FROM 'object'
 THEN RAISE EXCEPTION 'P3 page append rejected' USING ERRCODE='42501'; END IF;
 d1:=progress.last_d1+row_count;
 d2:=(item->>'d2')::bigint;
 item_digest:=item->>'digest';
 old_event_id:=(item->>'original_event_id')::uuid;
 new_event_id:=(item->>'effective_event_id')::uuid;
 new_play_id:=(item->>'effective_play_row_id')::uuid;
 original_eval:=source_item->'original_evaluation';
 effective_eval:=source_item->'evaluation';
 IF (item->>'d1')::bigint IS DISTINCT FROM d1 OR d2<=prior_d2
 OR (source_item->>'d1')::bigint IS DISTINCT FROM d1
 OR item_digest !~ '^[a-f0-9]{64}$'
 OR source_item->>'original_event_id' IS DISTINCT FROM old_event_id::text
 OR source_item->>'effective_event_id' IS DISTINCT FROM new_event_id::text
 OR source_item->>'effective_play_row_id' IS DISTINCT FROM new_play_id::text
 OR source_item->>'original_evaluation_digest' !~ '^[a-f0-9]{64}$'
 OR source_item->>'evaluation_digest' !~ '^[a-f0-9]{64}$'
 OR pg_catalog.jsonb_typeof(original_eval) IS DISTINCT FROM 'object'
 OR pg_catalog.jsonb_typeof(effective_eval) IS DISTINCT FROM 'object'
 OR original_eval->>'source_event_id' IS DISTINCT FROM old_event_id::text
 OR effective_eval->>'source_event_id' IS DISTINCT FROM new_event_id::text
 THEN RAISE EXCEPTION 'P3 page append rejected' USING ERRCODE='42501'; END IF;
 SELECT e.* INTO STRICT old_event FROM public.operation_events e
 WHERE (e.tenant_id,e.game_id,e.id)=(p_tenant_id,p_game_id,old_event_id)
 AND e.event_kind='play_input' AND e.ledger_kind='accepted'
 AND NOT e.is_tombstone AND e.generation=progress.internal_generation
 AND e.d1=d1 AND e.d2=d2 AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND NOT e.migration_unverified;
 IF NOT EXISTS(SELECT 1 FROM public.event_slots slot
 WHERE (slot.tenant_id,slot.game_id,slot.generation,slot.d1)=
 (p_tenant_id,p_game_id,progress.internal_generation,d1)
 AND slot.confirmed_version=CASE WHEN d1=progress.target_d1 THEN 2 ELSE 1 END)
 THEN RAISE EXCEPTION 'P3 page append rejected' USING ERRCODE='42501'; END IF;
 SELECT p.* INTO STRICT old_play FROM public.play_rows p
 WHERE (p.tenant_id,p.game_id,p.id)=
 (p_tenant_id,p_game_id,(item->>'original_play_row_id')::uuid)
 AND p.source_event_id=old_event_id AND p.hidden_at IS NULL
 AND p.import_batch_id IS NULL AND NOT p.migration_unverified;
 SELECT h.* INTO STRICT old_history FROM sync_fence.ordinary_pitch_history h
 WHERE (h.tenant_id,h.game_id,h.internal_generation,h.source_event_id,h.d1)=
 (p_tenant_id,p_game_id,progress.internal_generation,old_event_id,d1)
 AND h.history_version=old_cp.history_version;
 SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(r) ORDER BY r.base),
 '[]'::jsonb) INTO old_runners FROM public.play_runners r
 WHERE r.tenant_id=p_tenant_id AND r.play_id=old_play.id;
 SELECT s.* INTO STRICT old_source FROM sync_fence.stats_primitive_sources s
 WHERE (s.tenant_id,s.game_id,s.fact_version_id,s.source_event_id)=
 (p_tenant_id,p_game_id,old_stats.id,old_event_id)
 AND s.recording_generation=progress.internal_generation AND s.d1=d1;
 IF item->'original_payload' IS DISTINCT FROM old_event.payload
 OR item->'original_history_entry' IS DISTINCT FROM old_history.entry
 OR item->'original_play_row' IS DISTINCT FROM pg_catalog.to_jsonb(old_play)
 OR item->'original_play_runners' IS DISTINCT FROM old_runners
 OR original_eval IS DISTINCT FROM old_source.metric_states
 OR original_eval->>'native_rule_sha256' IS DISTINCT FROM old_source.rule_sha256
 OR old_source.play_row_id IS DISTINCT FROM old_play.id
 OR old_source.d2 IS DISTINCT FROM d2
 OR old_source.evaluation_sha256 IS DISTINCT FROM pg_catalog.encode(
 pg_catalog.sha256(pg_catalog.convert_to(original_eval::text,'UTF8')),'hex')
 THEN RAISE EXCEPTION 'P3 page append rejected' USING ERRCODE='42501'; END IF;
 IF d1=progress.target_d1 THEN
 IF new_event_id IS DISTINCT FROM change_event.id OR new_play_id=old_play.id
 OR item->>'state' IS DISTINCT FROM 'corrected'
 OR change_event.payload->>'targetEventId' IS DISTINCT FROM old_event_id::text
 OR pg_catalog.jsonb_typeof(item->'play_runners') IS DISTINCT FROM 'array'
 OR item->'play_row'->>'source_event_id' IS DISTINCT FROM new_event_id::text
 OR item->'play_row'->>'id' IS DISTINCT FROM new_play_id::text
 OR pg_catalog.jsonb_array_length(item->'play_runners')<>0
 THEN RAISE EXCEPTION 'P3 page append rejected' USING ERRCODE='42501'; END IF;
 INSERT INTO sync_fence.p3_projection_write_admissions(
 tenant_id,attempt_id,phase_id,game_id,internal_generation,capsule_id,
 change_event_id,play_row_id,ledger_fingerprint,expected_play_row,
 transaction_id,state)
 VALUES(p_tenant_id,p_attempt_id,p_phase_id,p_game_id,
 progress.internal_generation,p_capsule_id,change_event.id,new_play_id,
 c->>'ledger_fingerprint',item->'play_row',own_xid,'ready');
 IF item->'play_row'->'hidden_at' IS DISTINCT FROM 'null'::jsonb
 OR item->'play_row'->'import_batch_id' IS DISTINCT FROM 'null'::jsonb
 OR item->'play_row'->'legacy_row_identifier' IS DISTINCT FROM 'null'::jsonb
 OR item->'play_row'->'migration_unverified' IS DISTINCT FROM 'false'::jsonb THEN
 RAISE EXCEPTION 'P3 page append rejected' USING ERRCODE='42501'; END IF;
 INSERT INTO public.play_rows (batted_ball_strength,batted_ball_type,batter_id,batter_status,batting_order,batting_result_key,batting_side,catcher_id,comment,course_x,course_y,error_type,event_kind,fake_run,game_id,hit_x,hit_y,id,pickoff_detail,pickoff_type,pitch_speed,pitch_type_key,pitcher_id,play_number,press,raw_error_position,raw_fielder_position,resolved_error_player_id,resolved_fielder_id,secondary_batting_result_key,source_event_id,stance,strategy_detail_key,strategy_key,strategy_result_key,tenant_id,version)
 SELECT r.batted_ball_strength,r.batted_ball_type,r.batter_id,r.batter_status,r.batting_order,r.batting_result_key,r.batting_side,r.catcher_id,r.comment,r.course_x,r.course_y,r.error_type,r.event_kind,r.fake_run,r.game_id,r.hit_x,r.hit_y,r.id,r.pickoff_detail,r.pickoff_type,r.pitch_speed,r.pitch_type_key,r.pitcher_id,r.play_number,r.press,r.raw_error_position,r.raw_fielder_position,r.resolved_error_player_id,r.resolved_fielder_id,r.secondary_batting_result_key,r.source_event_id,r.stance,r.strategy_detail_key,r.strategy_key,r.strategy_result_key,r.tenant_id,r.version FROM pg_catalog.jsonb_populate_record(
 NULL::public.play_rows,item->'play_row') r;
 IF NOT EXISTS(SELECT 1 FROM sync_fence.p3_projection_write_admissions a
 WHERE (a.tenant_id,a.attempt_id,a.phase_id)=
 (p_tenant_id,p_attempt_id,p_phase_id) AND a.state='consumed'
 AND a.transaction_id=own_xid)
 THEN RAISE EXCEPTION 'P3 page append rejected' USING ERRCODE='42501'; END IF;
 ELSE
 IF new_event_id IS DISTINCT FROM old_event_id
 OR new_play_id IS DISTINCT FROM old_play.id
 OR item->'play_row' IS DISTINCT FROM pg_catalog.to_jsonb(old_play)
 OR item->'play_runners' IS DISTINCT FROM old_runners
 THEN RAISE EXCEPTION 'P3 page append rejected' USING ERRCODE='42501'; END IF;
 END IF;
 INSERT INTO sync_fence.p3_projection_page_rows(
 tenant_id,game_id,internal_generation,capsule_id,attempt_id,phase_id,
 device_id,binding_nonce,transaction_id,d5,ledger_fingerprint,d1,d2,
 original_event_id,effective_event_id,effective_play_row_id,item,
 original_evaluation,original_evaluation_digest,evaluation,evaluation_digest,
 item_digest)
 VALUES(p_tenant_id,p_game_id,progress.internal_generation,p_capsule_id,
 p_attempt_id,p_phase_id,p_device_id,p_binding_nonce,own_xid,binding.d5,
 c->>'ledger_fingerprint',d1,d2,old_event_id,new_event_id,new_play_id,item,
 original_eval,source_item->>'original_evaluation_digest',effective_eval,
 source_item->>'evaluation_digest',item_digest);
 source_hash:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
 source_hash||':'||d1::text||':'||item_digest,'UTF8')),'hex');
 evaluation_hash:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
 evaluation_hash||':'||d1::text||':'||
 (source_item->>'original_evaluation_digest')||':'||
 (source_item->>'evaluation_digest'),'UTF8')),'hex');
 prior_d2:=d2;
 END LOOP;
 UPDATE sync_fence.p3_projection_page_progress p SET
 item_count=p.item_count+row_count,last_d1=p.last_d1+row_count,last_d2=prior_d2,
 page_count=p.page_count+1,source_page_seal=source_hash,
 evaluation_page_seal=evaluation_hash
 WHERE (p.tenant_id,p.game_id,p.internal_generation,p.capsule_id)=
 (p_tenant_id,p_game_id,progress.internal_generation,p_capsule_id)
 AND p.state='building' AND p.item_count=progress.item_count
 AND p.last_d2=progress.last_d2 AND p.source_page_seal=progress.source_page_seal
 AND p.evaluation_page_seal=progress.evaluation_page_seal
 AND p.transaction_id=own_xid;
 IF NOT FOUND THEN RAISE EXCEPTION 'P3 page append rejected'
 USING ERRCODE='42501'; END IF;
 PERFORM sync_fence_api.assert_writer_binding(p_tenant_id,p_attempt_id,p_phase_id,
 p_binding_nonce,p_device_id,p_game_id);
 RETURN QUERY SELECT progress.last_d1+row_count,source_hash,evaluation_hash;
END;
$p3_page_append$;
ALTER FUNCTION sync_right_api.append_p3_projection_page(
 uuid,uuid,uuid,bytea,uuid,uuid,uuid,text)
 OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.append_p3_projection_page(
 uuid,uuid,uuid,bytea,uuid,uuid,uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_right_api.append_p3_projection_page(
 uuid,uuid,uuid,bytea,uuid,uuid,uuid,text) TO pitchlog_app;
