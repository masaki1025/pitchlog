-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_fence_api:retire_sync_attempt(uuid, uuid, uuid, uuid, uuid, text, bigint, text, text, uuid, bigint)

CREATE FUNCTION sync_fence_api.retire_sync_attempt(p_tenant_id uuid,p_attempt_id uuid,p_device_id uuid,p_game_id uuid,p_d5 uuid,p_wire_d4 text,p_codec_version bigint,p_request_fingerprint text,p_event_fingerprint text,p_authority_id uuid,p_recovery_generation bigint)
RETURNS text LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
DECLARE b sync_fence.writer_bindings%ROWTYPE; existing sync_fence.attempt_retirements%ROWTYPE; observed text;
BEGIN
 IF session_user<>'pitchlog_sync_binding_actor' OR current_setting('transaction_isolation')<>'read committed'
 OR p_tenant_id IS NULL OR p_attempt_id IS NULL OR p_device_id IS NULL OR p_game_id IS NULL OR p_d5 IS NULL
 OR p_wire_d4 IS NULL OR p_wire_d4='' OR p_codec_version IS NULL OR p_codec_version<=0
 OR p_request_fingerprint IS NULL OR p_request_fingerprint='' OR p_event_fingerprint IS NULL OR p_event_fingerprint='' OR p_authority_id IS NULL
 OR p_recovery_generation IS NULL OR p_recovery_generation<=0 THEN
  RAISE EXCEPTION 'attempt retirement rejected' USING ERRCODE='42501';
 END IF;
 PERFORM pg_advisory_xact_lock(hashtext(p_tenant_id::text),hashtext(p_attempt_id::text));
 IF NOT EXISTS(SELECT FROM public.rg1_restore_gate g WHERE g.singleton_id=1 AND g.state='open' AND g.recovery_generation=p_recovery_generation) THEN
  RETURN 'unresolved';
 END IF;
 FOR b IN SELECT w.* FROM sync_fence.writer_bindings w WHERE w.tenant_id=p_tenant_id AND w.attempt_id=p_attempt_id LOOP
  IF b.device_id IS DISTINCT FROM p_device_id OR b.game_id IS DISTINCT FROM p_game_id OR b.d5 IS DISTINCT FROM p_d5
  OR b.wire_d4 IS DISTINCT FROM p_wire_d4 OR b.codec_version IS DISTINCT FROM p_codec_version
  OR b.request_fingerprint IS DISTINCT FROM p_request_fingerprint OR b.event_fingerprint IS DISTINCT FROM p_event_fingerprint
  OR b.authority_id IS DISTINCT FROM p_authority_id OR b.issuer IS DISTINCT FROM p_authority_id
  OR b.recovery_generation IS DISTINCT FROM p_recovery_generation OR b.state<>'closed' OR b.close_id IS NULL THEN
   RETURN 'unresolved';
  END IF;
  SELECT o.outcome INTO observed FROM sync_fence_api.observe_writer_binding(p_tenant_id,p_attempt_id,b.phase_id,b.lease_id,b.close_id) o;
  IF observed NOT IN ('COMMITTED','ROLLBACK_CONFIRMED') OR observed IS NULL THEN RETURN 'unresolved'; END IF;
 END LOOP;
 SELECT t.* INTO existing FROM sync_fence.attempt_retirements t WHERE t.tenant_id=p_tenant_id AND t.attempt_id=p_attempt_id;
 IF FOUND THEN
  IF existing.device_id IS DISTINCT FROM p_device_id OR existing.game_id IS DISTINCT FROM p_game_id OR existing.d5 IS DISTINCT FROM p_d5
  OR existing.wire_d4 IS DISTINCT FROM p_wire_d4 OR existing.codec_version IS DISTINCT FROM p_codec_version
  OR existing.request_fingerprint IS DISTINCT FROM p_request_fingerprint OR existing.event_fingerprint IS DISTINCT FROM p_event_fingerprint
  OR existing.authority_id IS DISTINCT FROM p_authority_id
  OR existing.recovery_generation IS DISTINCT FROM p_recovery_generation THEN
   RAISE EXCEPTION 'attempt retirement identity rejected' USING ERRCODE='42501';
  END IF;
  RETURN 'retired';
 END IF;
 INSERT INTO sync_fence.attempt_retirements
 (tenant_id,attempt_id,device_id,game_id,d5,authority_id,wire_d4,codec_version,request_fingerprint,event_fingerprint,recovery_generation)
 VALUES (p_tenant_id,p_attempt_id,p_device_id,p_game_id,p_d5,p_authority_id,p_wire_d4,p_codec_version,p_request_fingerprint,p_event_fingerprint,p_recovery_generation);
 RETURN 'retired';
END;$f$;
ALTER FUNCTION sync_fence_api.retire_sync_attempt(uuid, uuid, uuid, uuid, uuid, text, bigint, text, text, uuid, bigint) OWNER TO pitchlog_sync_binding_fn_owner;
REVOKE ALL ON FUNCTION sync_fence_api.retire_sync_attempt(uuid, uuid, uuid, uuid, uuid, text, bigint, text, text, uuid, bigint) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_fence_api.retire_sync_attempt(uuid, uuid, uuid, uuid, uuid, text, bigint, text, text, uuid, bigint) TO pitchlog_sync_binding_actor;
