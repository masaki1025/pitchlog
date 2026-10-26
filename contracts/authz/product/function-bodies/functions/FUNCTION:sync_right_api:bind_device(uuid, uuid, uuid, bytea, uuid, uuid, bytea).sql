-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:bind_device(uuid, uuid, uuid, bytea, uuid, uuid, bytea)

CREATE FUNCTION sync_right_api.bind_device(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding_nonce bytea,p_device_id uuid,p_game_id uuid,p_credential_digest bytea)
RETURNS TABLE (device_matches boolean) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog,pg_temp AS $function$
DECLARE stored_digest bytea; revoked timestamptz;
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

IF p_credential_digest IS NULL OR
 pg_catalog.octet_length(p_credential_digest) <> 32 THEN
 RAISE EXCEPTION 'sync credential input rejected' USING ERRCODE='42501';
END IF;
SELECT d.credential_digest,d.revoked_at INTO stored_digest,revoked
 FROM public.trusted_devices d
 WHERE d.tenant_id=p_tenant_id AND d.device_id=p_device_id FOR SHARE;
RETURN QUERY SELECT COALESCE(FOUND AND revoked IS NULL AND
 stored_digest=p_credential_digest,false);
END;
$function$;
ALTER FUNCTION sync_right_api.bind_device(uuid, uuid, uuid, bytea, uuid, uuid, bytea) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.bind_device(uuid, uuid, uuid, bytea, uuid, uuid, bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_right_api.bind_device(uuid, uuid, uuid, bytea, uuid, uuid, bytea) TO pitchlog_app;
