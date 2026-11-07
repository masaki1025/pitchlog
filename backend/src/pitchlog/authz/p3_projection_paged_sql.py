"""P3 26件超の私有page保存・読取SQL候補を閉じた形で描画する。"""

from __future__ import annotations

from pitchlog.authz.p3_projection_sql import _bind_health
from pitchlog.authz.stats_primitive_sql import _ROOT, _verified_inputs
from pitchlog.authz.sync_right_sql import _COMMON


def candidate_paged_begin_sql() -> str:
    """真正T2後の同TXで不完全progressだけを開始する候補。"""
    _, _, model, artifact = _verified_inputs(_ROOT)
    return (
        _BEGIN_SQL.replace("__COMMON__", _COMMON)
        .replace("__MODEL__", model)
        .replace("__ARTIFACT__", artifact)
    )


def candidate_paged_append_sql() -> str:
    """1..25件の元原本と唯一T5を同TX私有stageへ追記する候補。"""
    return _APPEND_SQL.replace("__COMMON__", _COMMON)


def candidate_paged_finalize_sql(*, health_sql: str) -> str:
    """頁連鎖・完成版T5・current CP/headを一TXで確定する候補。"""
    _, _, model, artifact = _verified_inputs(_ROOT)
    health = _bind_health(health_sql)
    return (
        _FINALIZE_SQL.replace("__COMMON__", _COMMON)
        .replace("__HEALTH__", health)
        .replace("__MODEL__", model)
        .replace("__ARTIFACT__", artifact)
    )


_BEGIN_SQL = """CREATE FUNCTION sync_right_api.begin_p3_projection_page(
__COMMON__,p_capsule_header text,p_stats_header text)
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
 OR t->>'model_sha256' IS DISTINCT FROM '__MODEL__'
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
 (p_tenant_id,p_game_id,'__MODEL__')
 AND v.is_current AND v.invalidated_at IS NULL
 AND v.source_count=expected_watermark
 AND v.t5_artifact_set_sha256='__ARTIFACT__' FOR UPDATE;
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
"""


_APPEND_SQL = """CREATE FUNCTION sync_right_api.append_p3_projection_page(
__COMMON__,p_capsule_id uuid,p_page_json text)
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
 INSERT INTO public.play_rows SELECT (pg_catalog.jsonb_populate_record(
 NULL::public.play_rows,item->'play_row')).*;
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
"""


_FINALIZE_SQL = """CREATE FUNCTION sync_right_api.finalize_p3_projection_page(
__COMMON__,p_capsule_id uuid)
RETURNS TABLE(capsule_id uuid,checkpoint_digest text,evaluation_set_digest text,
 stats_version_id uuid) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_page_finalize$
#variable_conflict use_variable
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
 'p3-stats-chain-v2:'||p_capsule_id::text||':__MODEL__:'||
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
 AND v.model_sha256='__MODEL__' AND v.t5_artifact_set_sha256='__ARTIFACT__'
 FOR UPDATE;
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
 source_set_digest,stats_evaluation_set_digest,stats_model_sha256,
 stats_version_id,watermark,created_at)
 VALUES(p_tenant_id,p_game_id,p.internal_generation,p_capsule_id,
 (c->>'change_event_id')::uuid,binding.d5,p.target_d1,1,old_cp.id,
 old_cp.revision,old_cp.content_digest,old_cp.content,
 (c->'next_checkpoint'->>'id')::uuid,
 (c->'next_checkpoint'->>'revision')::bigint,
 c->'next_checkpoint'->>'content_digest',c->'next_checkpoint',
 source_digest,evaluation_digest,'__MODEL__',new_id,p.watermark,now_at);
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
 SELECT * INTO STRICT health FROM (__HEALTH__) actual_p3_health;
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
"""
