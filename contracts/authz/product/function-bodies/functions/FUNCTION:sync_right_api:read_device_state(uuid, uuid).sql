-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:read_device_state(uuid, uuid)

CREATE FUNCTION sync_right_api.read_device_state(
 p_tenant_id uuid,p_device_id uuid)
RETURNS TABLE(device_active boolean) LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $read_device_state$
BEGIN
 IF session_user <> 'pitchlog_app' OR current_user <> 'pitchlog_sync_right_fn_owner'
  OR p_tenant_id IS NULL OR p_device_id IS NULL
  OR p_tenant_id IS DISTINCT FROM
   NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid THEN
  RAISE EXCEPTION 'sync device state input rejected' USING ERRCODE='42501';
 END IF;
 RETURN QUERY SELECT EXISTS (
  SELECT 1 FROM public.trusted_devices d
  WHERE d.tenant_id=p_tenant_id AND d.device_id=p_device_id
   AND d.revoked_at IS NULL);
END;
$read_device_state$;
ALTER FUNCTION sync_right_api.read_device_state(uuid, uuid) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.read_device_state(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_right_api.read_device_state(uuid, uuid) TO pitchlog_app;
