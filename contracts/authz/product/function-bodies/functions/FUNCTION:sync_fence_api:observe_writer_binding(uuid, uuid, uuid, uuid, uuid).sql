-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_fence_api:observe_writer_binding(uuid, uuid, uuid, uuid, uuid)

CREATE FUNCTION sync_fence_api.observe_writer_binding(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_lease_id uuid,p_close_id uuid)
RETURNS TABLE(outcome text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
DECLARE r sync_fence.writer_bindings%ROWTYPE; admission_count bigint; matching_count bigint; xid_status text;
BEGIN
 IF session_user<>'pitchlog_sync_binding_actor' OR current_setting('transaction_isolation')<>'read committed' THEN RAISE EXCEPTION 'writer observation rejected' USING ERRCODE='42501'; END IF;
 SELECT b.* INTO STRICT r FROM sync_fence.writer_bindings b WHERE b.tenant_id=p_tenant_id AND b.attempt_id=p_attempt_id AND b.phase_id=p_phase_id AND b.lease_id=p_lease_id;
 IF r.state<>'closed' OR r.close_id IS DISTINCT FROM p_close_id OR r.postmaster_started_at<>pg_postmaster_start_time()
 OR NOT EXISTS(SELECT FROM pg_control_system() c CROSS JOIN pg_database d WHERE d.datname=current_database() AND c.system_identifier::text=r.system_identifier AND d.oid::text=r.database_oid)
 OR NOT EXISTS(SELECT FROM public.rg1_restore_gate g WHERE g.singleton_id=1 AND g.state='open' AND g.recovery_generation=r.recovery_generation) THEN RETURN QUERY SELECT 'UNKNOWN'::text; RETURN; END IF;
 SELECT count(*),count(*) FILTER(WHERE a.lease_id=r.lease_id AND a.transaction_id=r.transaction_id) INTO admission_count,matching_count FROM sync_fence.writer_admissions a WHERE a.tenant_id=p_tenant_id AND a.attempt_id=p_attempt_id AND a.phase_id=p_phase_id;
 -- statusは保存済み実xidだけを照会する。caller提供の任意xid照会口を作らない。
 xid_status:=pg_xact_status(r.transaction_id::xid8);
 RETURN QUERY SELECT CASE WHEN admission_count=1 AND matching_count=1 AND (xid_status IS NULL OR xid_status='committed') THEN 'COMMITTED'
 WHEN admission_count=0 AND xid_status='aborted' THEN 'ROLLBACK_CONFIRMED'
 WHEN admission_count=0 AND xid_status IN ('in progress','committed') THEN 'ENTRY_CLOSED_UNADMITTED' ELSE 'UNKNOWN' END;
END;$f$;
ALTER FUNCTION sync_fence_api.observe_writer_binding(uuid, uuid, uuid, uuid, uuid) OWNER TO pitchlog_sync_binding_fn_owner;
REVOKE ALL ON FUNCTION sync_fence_api.observe_writer_binding(uuid, uuid, uuid, uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_fence_api.observe_writer_binding(uuid, uuid, uuid, uuid, uuid) TO pitchlog_sync_binding_actor;
