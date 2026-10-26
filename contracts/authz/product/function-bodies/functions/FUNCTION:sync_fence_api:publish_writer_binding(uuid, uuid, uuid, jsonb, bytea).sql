-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_fence_api:publish_writer_binding(uuid, uuid, uuid, jsonb, bytea)

CREATE FUNCTION sync_fence_api.publish_writer_binding(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding jsonb,p_nonce_digest bytea)
RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
DECLARE r sync_fence.writer_bindings%ROWTYPE; observed_system text; observed_oid text;
BEGIN
 IF session_user<>'pitchlog_sync_binding_actor' OR p_tenant_id IS NULL OR p_attempt_id IS NULL OR p_phase_id IS NULL OR p_nonce_digest IS NULL OR octet_length(p_nonce_digest)<>32
 OR jsonb_typeof(p_binding) IS DISTINCT FROM 'object' OR ARRAY(SELECT jsonb_object_keys(p_binding) ORDER BY 1) IS DISTINCT FROM ARRAY['authority_id','backend_pid','backend_start','business_instance','codec_version','control_instance','control_version','d5','database_oid','device_id','event_fingerprint','expires_at','game_id','internal_generation','issuer','lease_id','postmaster_started_at','recovery_generation','request_fingerprint','restore_epoch','system_identifier','transaction_id','wire_d4']::text[] THEN
  RAISE EXCEPTION 'writer publication rejected' USING ERRCODE='42501';
 END IF;
 -- JSONは固定関数の閉じた内部形式。欠損/nullはNOT NULL/有限CHECKでも拒否する。
 r:=jsonb_populate_record(NULL::sync_fence.writer_bindings,p_binding);
 SELECT c.system_identifier::text,d.oid::text INTO STRICT observed_system,observed_oid FROM pg_control_system() c CROSS JOIN pg_database d WHERE d.datname=current_database();
 IF r.system_identifier IS DISTINCT FROM observed_system OR r.database_oid IS DISTINCT FROM observed_oid OR r.postmaster_started_at IS DISTINCT FROM pg_postmaster_start_time()
 OR r.expires_at IS NULL OR r.expires_at<=clock_timestamp() OR r.expires_at>clock_timestamp()+interval '30 seconds'
 OR NOT EXISTS(SELECT FROM public.rg1_restore_gate g WHERE g.singleton_id=1 AND g.state='open' AND g.recovery_generation=r.recovery_generation) THEN
  RAISE EXCEPTION 'writer publication identity rejected' USING ERRCODE='42501';
 END IF;
 r.tenant_id:=p_tenant_id; r.attempt_id:=p_attempt_id; r.phase_id:=p_phase_id; r.nonce_digest:=p_nonce_digest; r.state:='open'; r.close_id:=NULL;
 INSERT INTO sync_fence.writer_bindings SELECT r.*;
END;$f$;
ALTER FUNCTION sync_fence_api.publish_writer_binding(uuid, uuid, uuid, jsonb, bytea) OWNER TO pitchlog_sync_binding_fn_owner;
REVOKE ALL ON FUNCTION sync_fence_api.publish_writer_binding(uuid, uuid, uuid, jsonb, bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_fence_api.publish_writer_binding(uuid, uuid, uuid, jsonb, bytea) TO pitchlog_sync_binding_actor;
