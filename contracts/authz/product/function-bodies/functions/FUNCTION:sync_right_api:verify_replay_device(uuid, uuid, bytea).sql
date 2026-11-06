-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:verify_replay_device(uuid, uuid, bytea)

CREATE FUNCTION sync_right_api.verify_replay_device(
 p_tenant_id uuid,p_device_id uuid,p_credential_digest bytea)
RETURNS TABLE(device_matches boolean) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $verify_replay_device$
DECLARE stored_digest bytea; revoked timestamptz;
BEGIN
 IF session_user <> 'pitchlog_app' OR current_user <> 'pitchlog_sync_right_fn_owner'
  OR p_tenant_id IS NULL OR p_device_id IS NULL
  OR p_credential_digest IS NULL
  OR pg_catalog.octet_length(p_credential_digest) <> 32
  OR p_tenant_id IS DISTINCT FROM
   NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid THEN
  RAISE EXCEPTION 'sync replay device input rejected' USING ERRCODE='42501';
 END IF;

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
$verify_replay_device$;
ALTER FUNCTION sync_right_api.verify_replay_device(uuid, uuid, bytea) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.verify_replay_device(uuid, uuid, bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_right_api.verify_replay_device(uuid, uuid, bytea) TO pitchlog_app;
