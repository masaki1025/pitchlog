-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_fence_api:read_attempt_d5(uuid, uuid, text)

CREATE FUNCTION sync_fence_api.read_attempt_d5(p_tenant_id uuid,p_d5 uuid,p_event_fingerprint text)
RETURNS text LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
DECLARE stored_fingerprint text;
BEGIN
 IF session_user<>'pitchlog_sync_binding_actor' OR p_tenant_id IS NULL OR p_d5 IS NULL OR p_event_fingerprint IS NULL OR p_event_fingerprint='' OR current_setting('transaction_isolation')<>'read committed' THEN RAISE EXCEPTION 'attempt D5 observation rejected' USING ERRCODE='42501'; END IF;
 SELECT l.source_fingerprint INTO stored_fingerprint FROM public.idempotency_ledger l WHERE l.tenant_id=p_tenant_id AND l.d5=p_d5;
 IF NOT FOUND THEN RETURN 'absent'; END IF;
 IF stored_fingerprint IS DISTINCT FROM p_event_fingerprint THEN RETURN 'conflict'; END IF;
 RETURN 'matching';
END;$f$;
ALTER FUNCTION sync_fence_api.read_attempt_d5(uuid, uuid, text) OWNER TO pitchlog_sync_binding_fn_owner;
REVOKE ALL ON FUNCTION sync_fence_api.read_attempt_d5(uuid, uuid, text) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_fence_api.read_attempt_d5(uuid, uuid, text) TO pitchlog_sync_binding_actor;
