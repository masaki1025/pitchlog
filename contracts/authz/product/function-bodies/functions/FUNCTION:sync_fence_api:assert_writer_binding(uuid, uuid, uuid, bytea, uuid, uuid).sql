-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_fence_api:assert_writer_binding(uuid, uuid, uuid, bytea, uuid, uuid)

CREATE FUNCTION sync_fence_api.assert_writer_binding(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding_nonce bytea,p_device_id uuid,p_game_id uuid)
RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
DECLARE r sync_fence.writer_bindings%ROWTYPE; own_xid text; row_xmin text;
BEGIN
 IF session_user<>'pitchlog_app' OR p_tenant_id IS NULL OR p_tenant_id IS DISTINCT FROM NULLIF(current_setting('app.tenant_id',true),'')::uuid
 OR p_binding_nonce IS NULL OR octet_length(p_binding_nonce)<>32 THEN
  RAISE EXCEPTION 'writer assertion rejected' USING ERRCODE='42501';
 END IF;
 SELECT b.* INTO STRICT r FROM sync_fence.writer_bindings b WHERE b.tenant_id=p_tenant_id AND b.attempt_id=p_attempt_id AND b.phase_id=p_phase_id FOR SHARE;
 own_xid:=pg_current_xact_id()::text;
 IF r.state<>'open' OR r.expires_at<=clock_timestamp() OR r.nonce_digest<>sha256(p_binding_nonce)
 OR r.device_id IS DISTINCT FROM p_device_id OR r.game_id IS DISTINCT FROM p_game_id OR r.backend_pid<>pg_backend_pid() OR r.transaction_id<>own_xid
 OR r.postmaster_started_at<>pg_postmaster_start_time()

 OR NOT EXISTS(SELECT FROM pg_control_system() c CROSS JOIN pg_database d WHERE d.datname=current_database() AND c.system_identifier::text=r.system_identifier AND d.oid::text=r.database_oid)
 OR NOT EXISTS(SELECT FROM public.rg1_restore_gate g WHERE g.singleton_id=1 AND g.state='open' AND g.recovery_generation=r.recovery_generation) THEN
  RAISE EXCEPTION 'writer binding rejected' USING ERRCODE='42501';
 END IF;
 INSERT INTO sync_fence.writer_admissions(tenant_id,attempt_id,phase_id,lease_id,transaction_id)
 VALUES(p_tenant_id,p_attempt_id,p_phase_id,r.lease_id,own_xid) ON CONFLICT DO NOTHING;
 SELECT a.xmin::text INTO STRICT row_xmin FROM sync_fence.writer_admissions a WHERE a.tenant_id=p_tenant_id AND a.attempt_id=p_attempt_id AND a.phase_id=p_phase_id AND a.lease_id=r.lease_id AND a.transaction_id=own_xid;
 -- xid8は十進numericで扱う。INSERTがsubxidで起きた初回savepoint進入を拒否する。
 IF row_xmin::numeric<>mod(own_xid::numeric,4294967296::numeric) THEN
  RAISE EXCEPTION 'writer admission requires top-level transaction' USING ERRCODE='42501';
 END IF;
END;$f$;
ALTER FUNCTION sync_fence_api.assert_writer_binding(uuid, uuid, uuid, bytea, uuid, uuid) OWNER TO pitchlog_sync_binding_fn_owner;
REVOKE ALL ON FUNCTION sync_fence_api.assert_writer_binding(uuid, uuid, uuid, bytea, uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_fence_api.assert_writer_binding(uuid, uuid, uuid, bytea, uuid, uuid) TO pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_fence_api.assert_writer_binding(uuid, uuid, uuid, bytea, uuid, uuid) TO pitchlog_sync_right_fn_owner;
