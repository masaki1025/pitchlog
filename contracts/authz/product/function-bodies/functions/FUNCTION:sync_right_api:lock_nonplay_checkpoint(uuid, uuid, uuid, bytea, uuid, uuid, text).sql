-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:lock_nonplay_checkpoint(uuid, uuid, uuid, bytea, uuid, uuid, text)

CREATE FUNCTION sync_right_api.lock_nonplay_checkpoint(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding_nonce bytea,p_device_id uuid,p_game_id uuid,p_request_json text)
RETURNS TABLE(record_json text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $nonplay$
DECLARE stamp sync_fence.nonplay_write_admissions%ROWTYPE; own_xid text; p jsonb;
 cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE; 
BEGIN

IF session_user <> 'pitchlog_app' OR current_user <> 'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR p_attempt_id IS NULL OR p_phase_id IS NULL OR p_device_id IS NULL
 OR p_game_id IS NULL OR p_binding_nonce IS NULL
 OR pg_catalog.octet_length(p_binding_nonce) <> 32 THEN
 RAISE EXCEPTION 'sync writer binding rejected' USING ERRCODE='42501';
END IF;
-- 実関数未供給なら例外で閉じる。callerのnonceだけでは成功しない。
PERFORM sync_fence_api.assert_writer_binding(p_tenant_id,p_attempt_id,
 p_phase_id,p_binding_nonce,p_device_id,p_game_id);

 own_xid:=pg_catalog.pg_current_xact_id()::text;
 SELECT s.* INTO STRICT stamp FROM sync_fence.nonplay_write_admissions s
 JOIN sync_fence.writer_bindings b
 ON (b.tenant_id,b.attempt_id,b.phase_id)=(s.tenant_id,s.attempt_id,s.phase_id)
 JOIN sync_fence.writer_admissions a
 ON (a.tenant_id,a.attempt_id,a.phase_id)=(b.tenant_id,b.attempt_id,b.phase_id)
 WHERE (s.tenant_id,s.attempt_id,s.phase_id)=(p_tenant_id,p_attempt_id,p_phase_id)
 AND s.transaction_id=own_xid AND b.transaction_id=own_xid
 AND a.transaction_id=own_xid AND a.lease_id=b.lease_id
 AND b.state='open' AND b.expires_at>pg_catalog.clock_timestamp()
 AND a.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND s.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND s.tenant_id IS NOT DISTINCT FROM b.tenant_id AND s.attempt_id IS NOT DISTINCT FROM b.attempt_id AND s.phase_id IS NOT DISTINCT FROM b.phase_id AND s.authority_id IS NOT DISTINCT FROM b.authority_id AND s.control_instance IS NOT DISTINCT FROM b.control_instance AND s.business_instance IS NOT DISTINCT FROM b.business_instance AND s.restore_epoch IS NOT DISTINCT FROM b.restore_epoch AND s.control_version IS NOT DISTINCT FROM b.control_version AND s.issuer IS NOT DISTINCT FROM b.issuer AND s.lease_id IS NOT DISTINCT FROM b.lease_id AND s.device_id IS NOT DISTINCT FROM b.device_id AND s.game_id IS NOT DISTINCT FROM b.game_id AND s.wire_d4 IS NOT DISTINCT FROM b.wire_d4 AND s.internal_generation IS NOT DISTINCT FROM b.internal_generation AND s.recovery_generation IS NOT DISTINCT FROM b.recovery_generation AND s.codec_version IS NOT DISTINCT FROM b.codec_version AND s.request_fingerprint IS NOT DISTINCT FROM b.request_fingerprint AND s.d5 IS NOT DISTINCT FROM b.d5 AND s.event_fingerprint IS NOT DISTINCT FROM b.event_fingerprint AND s.system_identifier IS NOT DISTINCT FROM b.system_identifier AND s.database_oid IS NOT DISTINCT FROM b.database_oid AND s.postmaster_started_at IS NOT DISTINCT FROM b.postmaster_started_at AND s.backend_pid IS NOT DISTINCT FROM b.backend_pid AND s.backend_start IS NOT DISTINCT FROM b.backend_start AND s.transaction_id IS NOT DISTINCT FROM b.transaction_id AND s.nonce_digest IS NOT DISTINCT FROM b.nonce_digest AND s.expires_at IS NOT DISTINCT FROM b.expires_at FOR UPDATE OF s;
 IF NOT EXISTS(SELECT 1 FROM public.trusted_devices d
 WHERE d.tenant_id=p_tenant_id AND d.device_id=p_device_id AND d.revoked_at IS NULL)
 OR NOT EXISTS(SELECT 1 FROM public.recording_generations r
 WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id
 AND r.generation=stamp.internal_generation AND r.kind='normal'
 AND r.holder_device=p_device_id::text AND r.revoked_at IS NULL
 AND r.retired_at IS NULL AND r.import_batch_id IS NULL
 AND r.recovery_generation=stamp.recovery_generation)
 OR NOT EXISTS(SELECT 1 FROM public.rg1_restore_gate g
 WHERE g.singleton_id=1 AND g.state='open'
 AND g.recovery_generation=stamp.recovery_generation) THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;

 IF p_request_json IS NULL THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;
 p:=p_request_json::jsonb;

 IF stamp.state<>'right_verified' THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;
 SELECT c.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints c
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=stamp.internal_generation AND c.state='current'
 AND c.recovery_generation=stamp.recovery_generation FOR UPDATE;
 -- 旧v3からの真正導出はroot bootstrap adapterを要する。JSON形を偽装しない。
 IF cp.content->>'formatVersion' IS DISTINCT FROM 'nonplay-prefix-checkpoint-v1'
 AND cp.content->>'version' IS DISTINCT FROM '3'
 THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;
 IF cp.content->>'version'='3' AND EXISTS(SELECT 1 FROM public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
 AND e.generation=stamp.internal_generation AND e.d1<=cp.confirmed_watermark
 AND e.event_kind<>'play_input') THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;

 -- 既legacy/undoには新defaultを補完しない。presentなら全consumed原本へ閉じる。
 IF cp.content->>'formatVersion'='nonplay-prefix-checkpoint-v1' THEN
 IF EXISTS(SELECT 1 FROM
 pg_catalog.jsonb_array_elements(COALESCE(cp.content->'content'->'controlBridges','[]'::jsonb)) b(value)
 WHERE NOT EXISTS(SELECT 1 FROM (SELECT a.*,e.id AS original_id,r.issuance_order AS generation_order
 FROM sync_fence.lifecycle_write_admissions a
 JOIN public.operation_events e ON e.tenant_id=a.tenant_id AND e.game_id=a.game_id
 AND e.id=a.source_event_id AND e.generation=a.internal_generation AND e.d1=a.source_d1
 JOIN public.event_slots slot ON (slot.tenant_id,slot.game_id,slot.generation,slot.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN public.recording_generations r ON r.tenant_id=e.tenant_id AND r.game_id=e.game_id
 AND r.generation=e.generation
 JOIN public.recording_generations current_generation ON
 current_generation.tenant_id=r.tenant_id
 AND current_generation.game_id=r.game_id AND current_generation.generation=stamp.internal_generation
 JOIN sync_fence.writer_bindings original_binding
 ON (original_binding.tenant_id,original_binding.attempt_id,original_binding.phase_id)
 =(a.tenant_id,a.attempt_id,a.phase_id)
 WHERE a.tenant_id=p_tenant_id AND a.game_id=p_game_id AND a.state='consumed'
 AND a.consumed_at IS NOT NULL AND e.ledger_kind='accepted'
 AND e.event_kind=CASE WHEN a.action='end' THEN 'game_end_declaration' ELSE
 'game_reopen' END
 AND a.action IN ('end','reopen') AND e.d2=a.source_d2 AND e.d5=a.d5
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND slot.confirmed_version=1
 AND l.kind='accepted' AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND l.source_fingerprint=a.event_fingerprint AND e.xmin=a.xmin AND l.xmin=a.xmin
 AND a.tenant_id IS NOT DISTINCT FROM original_binding.tenant_id AND a.attempt_id IS NOT DISTINCT FROM original_binding.attempt_id AND a.phase_id IS NOT DISTINCT FROM original_binding.phase_id AND a.authority_id IS NOT DISTINCT FROM original_binding.authority_id AND a.control_instance IS NOT DISTINCT FROM original_binding.control_instance AND a.business_instance IS NOT DISTINCT FROM original_binding.business_instance AND a.restore_epoch IS NOT DISTINCT FROM original_binding.restore_epoch AND a.control_version IS NOT DISTINCT FROM original_binding.control_version AND a.issuer IS NOT DISTINCT FROM original_binding.issuer AND a.lease_id IS NOT DISTINCT FROM original_binding.lease_id AND a.device_id IS NOT DISTINCT FROM original_binding.device_id AND a.game_id IS NOT DISTINCT FROM original_binding.game_id AND a.wire_d4 IS NOT DISTINCT FROM original_binding.wire_d4 AND a.internal_generation IS NOT DISTINCT FROM original_binding.internal_generation AND a.recovery_generation IS NOT DISTINCT FROM original_binding.recovery_generation AND a.codec_version IS NOT DISTINCT FROM original_binding.codec_version AND a.request_fingerprint IS NOT DISTINCT FROM original_binding.request_fingerprint AND a.d5 IS NOT DISTINCT FROM original_binding.d5 AND a.event_fingerprint IS NOT DISTINCT FROM original_binding.event_fingerprint AND a.system_identifier IS NOT DISTINCT FROM original_binding.system_identifier AND a.database_oid IS NOT DISTINCT FROM original_binding.database_oid AND a.postmaster_started_at IS NOT DISTINCT FROM original_binding.postmaster_started_at AND a.backend_pid IS NOT DISTINCT FROM original_binding.backend_pid AND a.backend_start IS NOT DISTINCT FROM original_binding.backend_start AND a.transaction_id IS NOT DISTINCT FROM original_binding.transaction_id AND a.nonce_digest IS NOT DISTINCT FROM original_binding.nonce_digest AND a.expires_at IS NOT DISTINCT FROM original_binding.expires_at
 AND r.issuance_order<=current_generation.issuance_order
 AND (e.generation<>stamp.internal_generation OR e.d1<=cp.confirmed_watermark)
) a
 WHERE a.source_event_id=(b.value->'source'->>'eventId')::uuid
 AND a.frame_id=(b.value->>'frameId')::uuid
 AND a.action=b.value->>'action' AND a.wire_d4=b.value->'source'->>'generation'
 AND a.source_d1::text=b.value->'source'->>'d1'
 AND a.d5::text=b.value->'source'->>'d5'
 AND a.event_fingerprint=b.value->'source'->>'fingerprint'
 AND a.checkpoint_id::text=b.value->'checkpointBefore'->>'id'
 AND a.checkpoint_revision::text=b.value->'checkpointBefore'->>'revision'
 AND a.checkpoint_digest=b.value->'checkpointBefore'->>'digest'
 AND a.receipt_id::text=b.value->'kernel'->'request'->'event'->>'receiptId'
 AND a.source_event_id::text=b.value->'kernel'->'request'->'event'->>'eventId'
 AND b.value->'source'->>'gameId'=p_game_id::text
 AND a.preparation->'after_source'->'checkpoint'->'content'->'controlBridges'->-1
 =b.value
 AND a.preparation->'event_original'->'payload'=(SELECT e.payload FROM
 public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.id=a.source_event_id)))
 OR EXISTS(SELECT 1 FROM (SELECT a.*,e.id AS original_id,r.issuance_order AS generation_order
 FROM sync_fence.lifecycle_write_admissions a
 JOIN public.operation_events e ON e.tenant_id=a.tenant_id AND e.game_id=a.game_id
 AND e.id=a.source_event_id AND e.generation=a.internal_generation AND e.d1=a.source_d1
 JOIN public.event_slots slot ON (slot.tenant_id,slot.game_id,slot.generation,slot.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN public.recording_generations r ON r.tenant_id=e.tenant_id AND r.game_id=e.game_id
 AND r.generation=e.generation
 JOIN public.recording_generations current_generation ON
 current_generation.tenant_id=r.tenant_id
 AND current_generation.game_id=r.game_id AND current_generation.generation=stamp.internal_generation
 JOIN sync_fence.writer_bindings original_binding
 ON (original_binding.tenant_id,original_binding.attempt_id,original_binding.phase_id)
 =(a.tenant_id,a.attempt_id,a.phase_id)
 WHERE a.tenant_id=p_tenant_id AND a.game_id=p_game_id AND a.state='consumed'
 AND a.consumed_at IS NOT NULL AND e.ledger_kind='accepted'
 AND e.event_kind=CASE WHEN a.action='end' THEN 'game_end_declaration' ELSE
 'game_reopen' END
 AND a.action IN ('end','reopen') AND e.d2=a.source_d2 AND e.d5=a.d5
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND slot.confirmed_version=1
 AND l.kind='accepted' AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND l.source_fingerprint=a.event_fingerprint AND e.xmin=a.xmin AND l.xmin=a.xmin
 AND a.tenant_id IS NOT DISTINCT FROM original_binding.tenant_id AND a.attempt_id IS NOT DISTINCT FROM original_binding.attempt_id AND a.phase_id IS NOT DISTINCT FROM original_binding.phase_id AND a.authority_id IS NOT DISTINCT FROM original_binding.authority_id AND a.control_instance IS NOT DISTINCT FROM original_binding.control_instance AND a.business_instance IS NOT DISTINCT FROM original_binding.business_instance AND a.restore_epoch IS NOT DISTINCT FROM original_binding.restore_epoch AND a.control_version IS NOT DISTINCT FROM original_binding.control_version AND a.issuer IS NOT DISTINCT FROM original_binding.issuer AND a.lease_id IS NOT DISTINCT FROM original_binding.lease_id AND a.device_id IS NOT DISTINCT FROM original_binding.device_id AND a.game_id IS NOT DISTINCT FROM original_binding.game_id AND a.wire_d4 IS NOT DISTINCT FROM original_binding.wire_d4 AND a.internal_generation IS NOT DISTINCT FROM original_binding.internal_generation AND a.recovery_generation IS NOT DISTINCT FROM original_binding.recovery_generation AND a.codec_version IS NOT DISTINCT FROM original_binding.codec_version AND a.request_fingerprint IS NOT DISTINCT FROM original_binding.request_fingerprint AND a.d5 IS NOT DISTINCT FROM original_binding.d5 AND a.event_fingerprint IS NOT DISTINCT FROM original_binding.event_fingerprint AND a.system_identifier IS NOT DISTINCT FROM original_binding.system_identifier AND a.database_oid IS NOT DISTINCT FROM original_binding.database_oid AND a.postmaster_started_at IS NOT DISTINCT FROM original_binding.postmaster_started_at AND a.backend_pid IS NOT DISTINCT FROM original_binding.backend_pid AND a.backend_start IS NOT DISTINCT FROM original_binding.backend_start AND a.transaction_id IS NOT DISTINCT FROM original_binding.transaction_id AND a.nonce_digest IS NOT DISTINCT FROM original_binding.nonce_digest AND a.expires_at IS NOT DISTINCT FROM original_binding.expires_at
 AND r.issuance_order<=current_generation.issuance_order
 AND (e.generation<>stamp.internal_generation OR e.d1<=cp.confirmed_watermark)
) a WHERE NOT EXISTS(
 SELECT 1 FROM pg_catalog.jsonb_array_elements(COALESCE(cp.content->'content'->'controlBridges','[]'::jsonb)) b(value)
 WHERE b.value->'source'->>'eventId'=a.source_event_id::text))
 OR EXISTS(SELECT 1 FROM public.operation_events control_event
 JOIN public.recording_generations control_generation ON
 (control_generation.tenant_id,control_generation.game_id,control_generation.generation)
 =(control_event.tenant_id,control_event.game_id,control_event.generation)
 JOIN public.recording_generations selected_generation ON
 selected_generation.tenant_id=control_event.tenant_id
 AND selected_generation.game_id=control_event.game_id AND
 selected_generation.generation=stamp.internal_generation
 WHERE control_event.tenant_id=p_tenant_id AND control_event.game_id=p_game_id
 AND control_event.event_kind IN ('game_end_declaration','game_reopen')
 AND control_event.ledger_kind='accepted' AND control_event.replaced_at IS NULL
 AND control_event.retired_at IS NULL
 AND control_generation.issuance_order<=selected_generation.issuance_order
 AND (control_event.generation<>stamp.internal_generation OR
 control_event.d1<=cp.confirmed_watermark)
 AND NOT EXISTS(SELECT 1 FROM
 pg_catalog.jsonb_array_elements(COALESCE(cp.content->'content'->'controlBridges','[]'::jsonb)) b(value)
 WHERE b.value->'source'->>'eventId'=control_event.id::text))
 OR EXISTS(SELECT 1 FROM (SELECT count(*) AS n,count(DISTINCT
 value->'source'->>'eventId') AS unique_n
 FROM pg_catalog.jsonb_array_elements(COALESCE(cp.content->'content'->'controlBridges','[]'::jsonb)))
 duplicate_controls
 WHERE n<>unique_n)
 OR EXISTS(SELECT 1 FROM (
 SELECT a.generation_order,a.source_d1,
 lag(a.generation_order) OVER(ORDER BY b.ordinality) AS previous_generation,
 lag(a.source_d1) OVER(ORDER BY b.ordinality) AS previous_d1
 FROM pg_catalog.jsonb_array_elements(COALESCE(cp.content->'content'->'controlBridges','[]'::jsonb))
 WITH ORDINALITY b(value,ordinality)
 JOIN (SELECT a.*,e.id AS original_id,r.issuance_order AS generation_order
 FROM sync_fence.lifecycle_write_admissions a
 JOIN public.operation_events e ON e.tenant_id=a.tenant_id AND e.game_id=a.game_id
 AND e.id=a.source_event_id AND e.generation=a.internal_generation AND e.d1=a.source_d1
 JOIN public.event_slots slot ON (slot.tenant_id,slot.game_id,slot.generation,slot.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN public.recording_generations r ON r.tenant_id=e.tenant_id AND r.game_id=e.game_id
 AND r.generation=e.generation
 JOIN public.recording_generations current_generation ON
 current_generation.tenant_id=r.tenant_id
 AND current_generation.game_id=r.game_id AND current_generation.generation=stamp.internal_generation
 JOIN sync_fence.writer_bindings original_binding
 ON (original_binding.tenant_id,original_binding.attempt_id,original_binding.phase_id)
 =(a.tenant_id,a.attempt_id,a.phase_id)
 WHERE a.tenant_id=p_tenant_id AND a.game_id=p_game_id AND a.state='consumed'
 AND a.consumed_at IS NOT NULL AND e.ledger_kind='accepted'
 AND e.event_kind=CASE WHEN a.action='end' THEN 'game_end_declaration' ELSE
 'game_reopen' END
 AND a.action IN ('end','reopen') AND e.d2=a.source_d2 AND e.d5=a.d5
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND slot.confirmed_version=1
 AND l.kind='accepted' AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND l.source_fingerprint=a.event_fingerprint AND e.xmin=a.xmin AND l.xmin=a.xmin
 AND a.tenant_id IS NOT DISTINCT FROM original_binding.tenant_id AND a.attempt_id IS NOT DISTINCT FROM original_binding.attempt_id AND a.phase_id IS NOT DISTINCT FROM original_binding.phase_id AND a.authority_id IS NOT DISTINCT FROM original_binding.authority_id AND a.control_instance IS NOT DISTINCT FROM original_binding.control_instance AND a.business_instance IS NOT DISTINCT FROM original_binding.business_instance AND a.restore_epoch IS NOT DISTINCT FROM original_binding.restore_epoch AND a.control_version IS NOT DISTINCT FROM original_binding.control_version AND a.issuer IS NOT DISTINCT FROM original_binding.issuer AND a.lease_id IS NOT DISTINCT FROM original_binding.lease_id AND a.device_id IS NOT DISTINCT FROM original_binding.device_id AND a.game_id IS NOT DISTINCT FROM original_binding.game_id AND a.wire_d4 IS NOT DISTINCT FROM original_binding.wire_d4 AND a.internal_generation IS NOT DISTINCT FROM original_binding.internal_generation AND a.recovery_generation IS NOT DISTINCT FROM original_binding.recovery_generation AND a.codec_version IS NOT DISTINCT FROM original_binding.codec_version AND a.request_fingerprint IS NOT DISTINCT FROM original_binding.request_fingerprint AND a.d5 IS NOT DISTINCT FROM original_binding.d5 AND a.event_fingerprint IS NOT DISTINCT FROM original_binding.event_fingerprint AND a.system_identifier IS NOT DISTINCT FROM original_binding.system_identifier AND a.database_oid IS NOT DISTINCT FROM original_binding.database_oid AND a.postmaster_started_at IS NOT DISTINCT FROM original_binding.postmaster_started_at AND a.backend_pid IS NOT DISTINCT FROM original_binding.backend_pid AND a.backend_start IS NOT DISTINCT FROM original_binding.backend_start AND a.transaction_id IS NOT DISTINCT FROM original_binding.transaction_id AND a.nonce_digest IS NOT DISTINCT FROM original_binding.nonce_digest AND a.expires_at IS NOT DISTINCT FROM original_binding.expires_at
 AND r.issuance_order<=current_generation.issuance_order
 AND (e.generation<>stamp.internal_generation OR e.d1<=cp.confirmed_watermark)
) a ON a.source_event_id::text=b.value->'source'->>'eventId'
 ) ordered_controls WHERE previous_generation>generation_order
 OR (previous_generation=generation_order AND previous_d1>=source_d1))
 THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
 IF pg_catalog.jsonb_array_length(COALESCE(cp.content->'content'->'controlBridges','[]'::jsonb))>0 AND NOT EXISTS(
 SELECT 1 FROM sync_fence.game_lifecycle_heads lifecycle_head WHERE lifecycle_head.tenant_id=p_tenant_id
 AND lifecycle_head.game_id=p_game_id
 AND lifecycle_head.last_control_event_id::text=(cp.content->'content'->'controlBridges'->-1)->'source'->>'eventId'
 AND lifecycle_head.is_finished=((cp.content->'content'->'controlBridges'->-1)->>'action'='end')
 ) THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
 END IF;
 RETURN QUERY SELECT pg_catalog.jsonb_build_object(
 'checkpoint',cp.content,'storage',pg_catalog.jsonb_build_object('row',pg_catalog.to_jsonb(cp),
 'nextPhysicalPlayNumber',(SELECT (pg_catalog.max(pr.play_number)+1)::text
 FROM public.play_rows pr WHERE pr.tenant_id=p_tenant_id AND pr.game_id=p_game_id)),
 'generationChain',(SELECT pg_catalog.jsonb_agg(x.wire_d4 ORDER BY x.issuance_order)
 FROM (SELECT r.issuance_order, b.wire_d4
 FROM public.recording_generations r
 JOIN sync_fence.writer_bindings b ON b.tenant_id=r.tenant_id
 AND b.game_id=r.game_id AND b.internal_generation=r.generation
 WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id AND r.kind='normal'
 AND r.issuance_order<=(SELECT own.issuance_order
 FROM public.recording_generations own WHERE own.tenant_id=p_tenant_id
 AND own.game_id=p_game_id AND own.generation=stamp.internal_generation)
 GROUP BY r.issuance_order,b.wire_d4) x))::text;

END;
$nonplay$;

ALTER FUNCTION sync_right_api.lock_nonplay_checkpoint(uuid, uuid, uuid, bytea, uuid, uuid, text) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.lock_nonplay_checkpoint(uuid, uuid, uuid, bytea, uuid, uuid, text) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_right_api.lock_nonplay_checkpoint(uuid, uuid, uuid, bytea, uuid, uuid, text) TO pitchlog_app;
