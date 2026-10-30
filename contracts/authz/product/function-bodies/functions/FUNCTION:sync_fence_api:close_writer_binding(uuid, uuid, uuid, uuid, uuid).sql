-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_fence_api:close_writer_binding(uuid, uuid, uuid, uuid, uuid)

CREATE FUNCTION sync_fence_api.close_writer_binding(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_lease_id uuid,p_close_id uuid)
RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
DECLARE r sync_fence.writer_bindings%ROWTYPE;
BEGIN
 IF session_user<>'pitchlog_sync_binding_actor' OR p_close_id IS NULL THEN RAISE EXCEPTION 'writer close rejected' USING ERRCODE='42501'; END IF;
 SELECT b.* INTO STRICT r FROM sync_fence.writer_bindings b WHERE b.tenant_id=p_tenant_id AND b.attempt_id=p_attempt_id AND b.phase_id=p_phase_id AND b.lease_id=p_lease_id FOR UPDATE;
 IF r.state='closed' THEN
  IF r.close_id IS DISTINCT FROM p_close_id THEN RAISE EXCEPTION 'writer close identity rejected' USING ERRCODE='42501'; END IF;
  RETURN;
 END IF;
 UPDATE sync_fence.writer_bindings b SET state='closed',close_id=p_close_id WHERE b.tenant_id=p_tenant_id AND b.attempt_id=p_attempt_id AND b.phase_id=p_phase_id;
END;$f$;
ALTER FUNCTION sync_fence_api.close_writer_binding(uuid, uuid, uuid, uuid, uuid) OWNER TO pitchlog_sync_binding_fn_owner;
REVOKE ALL ON FUNCTION sync_fence_api.close_writer_binding(uuid, uuid, uuid, uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_fence_api.close_writer_binding(uuid, uuid, uuid, uuid, uuid) TO pitchlog_sync_binding_actor;
