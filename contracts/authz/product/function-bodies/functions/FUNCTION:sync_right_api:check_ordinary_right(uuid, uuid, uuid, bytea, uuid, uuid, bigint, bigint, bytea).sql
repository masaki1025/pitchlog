-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:check_ordinary_right(uuid, uuid, uuid, bytea, uuid, uuid, bigint, bigint, bytea)

CREATE FUNCTION sync_right_api.check_ordinary_right(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding_nonce bytea,p_device_id uuid,p_game_id uuid,p_internal_generation bigint,p_recovery_generation bigint,p_proof_digest bytea)
RETURNS TABLE (recovery_matches boolean,right_matches boolean) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog,pg_temp AS $function$
DECLARE current_epoch bigint; gate_state text; recovery_ok boolean; right_ok boolean;
 own_xid text; stamp_state text; row_xmin text;
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

IF p_internal_generation IS NULL OR p_internal_generation <= 0 OR
 p_recovery_generation IS NULL OR p_recovery_generation <= 0 OR
 p_proof_digest IS NULL OR pg_catalog.octet_length(p_proof_digest) <> 32 THEN
 RAISE EXCEPTION 'sync right input rejected' USING ERRCODE='42501';
END IF;
SELECT g.recovery_generation,g.state INTO STRICT current_epoch,gate_state
 FROM public.rg1_restore_gate g WHERE g.singleton_id=1;
IF current_epoch IS NULL OR gate_state <> 'open' THEN
 RAISE EXCEPTION 'sync recovery unavailable' USING ERRCODE='55000';
END IF;
recovery_ok := current_epoch = p_recovery_generation;
right_ok := false;
IF recovery_ok THEN
 right_ok := EXISTS (
 SELECT 1 FROM public.recording_generations r WHERE r.tenant_id=p_tenant_id
 AND r.game_id=p_game_id AND r.generation=p_internal_generation AND r.kind='normal'
 AND r.holder_device=p_device_id::text AND r.revoked_at IS NULL
 AND r.retired_at IS NULL AND r.recovery_generation=current_epoch
 AND r.proof_digest=p_proof_digest);
END IF;
own_xid := pg_catalog.pg_current_xact_id()::text;
SELECT s.state INTO stamp_state FROM sync_fence.ordinary_pitch_write_admissions s
 WHERE (s.tenant_id,s.attempt_id,s.phase_id)=(p_tenant_id,p_attempt_id,p_phase_id) FOR UPDATE;
IF NOT FOUND THEN
 INSERT INTO sync_fence.ordinary_pitch_write_admissions(tenant_id,attempt_id,phase_id,authority_id,control_instance,business_instance,restore_epoch,control_version,issuer,lease_id,device_id,game_id,wire_d4,internal_generation,recovery_generation,codec_version,request_fingerprint,d5,event_fingerprint,system_identifier,database_oid,postmaster_started_at,backend_pid,backend_start,transaction_id,nonce_digest,expires_at,state)
 SELECT b.tenant_id,b.attempt_id,b.phase_id,b.authority_id,b.control_instance,b.business_instance,b.restore_epoch,b.control_version,b.issuer,b.lease_id,b.device_id,b.game_id,b.wire_d4,b.internal_generation,b.recovery_generation,b.codec_version,b.request_fingerprint,b.d5,b.event_fingerprint,b.system_identifier,b.database_oid,b.postmaster_started_at,b.backend_pid,b.backend_start,b.transaction_id,b.nonce_digest,b.expires_at,'invalid'
 FROM sync_fence.writer_bindings b
 WHERE (b.tenant_id,b.attempt_id,b.phase_id)=(p_tenant_id,p_attempt_id,p_phase_id)
 AND b.transaction_id=own_xid
 RETURNING xmin::text INTO row_xmin;
ELSE
 UPDATE sync_fence.ordinary_pitch_write_admissions s SET state=CASE
  WHEN s.state IN ('device_verified','right_verified') AND recovery_ok AND right_ok
   AND s.internal_generation=p_internal_generation
   AND s.recovery_generation=p_recovery_generation THEN 'right_verified'
  WHEN s.state IN ('invalid','consumed') THEN s.state
  ELSE 'invalid' END
 WHERE (s.tenant_id,s.attempt_id,s.phase_id)=(p_tenant_id,p_attempt_id,p_phase_id)
 AND s.transaction_id=own_xid
 RETURNING s.xmin::text INTO row_xmin;
END IF;
IF NOT FOUND OR row_xmin IS NULL
 OR row_xmin::numeric<>pg_catalog.mod(own_xid::numeric,4294967296::numeric) THEN
 RAISE EXCEPTION 'first ball stamp rejected' USING ERRCODE='42501';
END IF;
RETURN QUERY SELECT recovery_ok,right_ok;
END;
$function$;

ALTER FUNCTION sync_right_api.check_ordinary_right(uuid, uuid, uuid, bytea, uuid, uuid, bigint, bigint, bytea) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.check_ordinary_right(uuid, uuid, uuid, bytea, uuid, uuid, bigint, bigint, bytea) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_right_api.check_ordinary_right(uuid, uuid, uuid, bytea, uuid, uuid, bigint, bigint, bytea) TO pitchlog_app;
