-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:check_current_right(uuid, uuid, uuid, bytea, uuid, uuid, bigint, bigint, bytea)

CREATE FUNCTION sync_right_api.check_current_right(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding_nonce bytea,p_device_id uuid,p_game_id uuid,p_internal_generation bigint,p_recovery_generation bigint,p_proof_digest bytea)
RETURNS TABLE (recovery_matches boolean,right_matches boolean) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog,pg_temp AS $function$
DECLARE current_epoch bigint; gate_state text;
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
IF current_epoch <> p_recovery_generation THEN
 RETURN QUERY SELECT false,false;
 RETURN;
END IF;
-- game→generation lockは既prefix核が保持。本関数で先取りしない。
RETURN QUERY SELECT true,EXISTS (
 SELECT 1 FROM public.recording_generations r WHERE r.tenant_id=p_tenant_id
 AND r.game_id=p_game_id AND r.generation=p_internal_generation AND r.kind='normal'
 AND r.holder_device=p_device_id::text AND r.revoked_at IS NULL
 AND r.retired_at IS NULL AND r.recovery_generation=current_epoch
 AND r.proof_digest=p_proof_digest);
END;
$function$;
ALTER FUNCTION sync_right_api.check_current_right(uuid, uuid, uuid, bytea, uuid, uuid, bigint, bigint, bytea) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.check_current_right(uuid, uuid, uuid, bytea, uuid, uuid, bigint, bigint, bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_right_api.check_current_right(uuid, uuid, uuid, bytea, uuid, uuid, bigint, bigint, bytea) TO pitchlog_app;
