-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_fence_api:read_writer_database_identity(uuid)

CREATE FUNCTION sync_fence_api.read_writer_database_identity(p_tenant_id uuid)
RETURNS TABLE(system_identifier text,database_oid text,postmaster_started_at timestamptz)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
BEGIN
 IF session_user<>'pitchlog_app' OR p_tenant_id IS NULL OR p_tenant_id IS DISTINCT FROM NULLIF(current_setting('app.tenant_id',true),'')::uuid THEN
  RAISE EXCEPTION 'writer database identity rejected' USING ERRCODE='42501';
 END IF;
 RETURN QUERY SELECT c.system_identifier::text,d.oid::text,pg_postmaster_start_time()
 FROM pg_control_system() c CROSS JOIN pg_database d WHERE d.datname=current_database();
END;$f$;
ALTER FUNCTION sync_fence_api.read_writer_database_identity(uuid) OWNER TO pitchlog_sync_binding_fn_owner;
REVOKE ALL ON FUNCTION sync_fence_api.read_writer_database_identity(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_fence_api.read_writer_database_identity(uuid) TO pitchlog_app;
