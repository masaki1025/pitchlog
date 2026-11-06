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
