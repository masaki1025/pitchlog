-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_fence_api:read_writer_identity(uuid)

CREATE FUNCTION sync_fence_api.read_writer_identity(p_tenant_id uuid)
RETURNS TABLE(system_identifier text,database_oid text,postmaster_started_at timestamptz,backend_pid integer,backend_start timestamptz,transaction_id text)
LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog,pg_temp AS $f$
BEGIN
 IF session_user<>'pitchlog_app' OR current_user<>'pitchlog_app' OR p_tenant_id IS NULL OR p_tenant_id IS DISTINCT FROM NULLIF(current_setting('app.tenant_id',true),'')::uuid THEN
  RAISE EXCEPTION 'writer identity rejected' USING ERRCODE='42501';
 END IF;
 RETURN QUERY SELECT c.system_identifier,c.database_oid,c.postmaster_started_at,pg_backend_pid(),a.backend_start,pg_current_xact_id()::text
 FROM sync_fence_api.read_writer_database_identity(p_tenant_id) c CROSS JOIN pg_stat_activity a WHERE a.pid=pg_backend_pid();
END;$f$;
ALTER FUNCTION sync_fence_api.read_writer_identity(uuid) OWNER TO pitchlog_sync_binding_fn_owner;
REVOKE ALL ON FUNCTION sync_fence_api.read_writer_identity(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_fence_api.read_writer_identity(uuid) TO pitchlog_app;
