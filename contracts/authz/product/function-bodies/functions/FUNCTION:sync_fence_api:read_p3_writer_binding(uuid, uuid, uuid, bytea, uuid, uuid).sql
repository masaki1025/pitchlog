-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_fence_api:read_p3_writer_binding(uuid, uuid, uuid, bytea, uuid, uuid)

CREATE FUNCTION sync_fence_api.read_p3_writer_binding(
 p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding_nonce bytea,
 p_device_id uuid,p_game_id uuid)
RETURNS TABLE(tenant_id uuid,d5 uuid,wire_d4 text,
 internal_generation bigint,event_fingerprint text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_binding$
DECLARE own_xid text;
BEGIN
 IF session_user<>'pitchlog_app'
 OR current_user<>'pitchlog_sync_binding_fn_owner'
 OR p_tenant_id IS NULL OR p_attempt_id IS NULL OR p_phase_id IS NULL
 OR p_device_id IS NULL OR p_game_id IS NULL OR p_binding_nonce IS NULL
 OR pg_catalog.octet_length(p_binding_nonce)<>32
 OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 THEN RAISE EXCEPTION 'P3 binding rejected' USING ERRCODE='42501'; END IF;
 PERFORM sync_fence_api.assert_writer_binding(
 p_tenant_id,p_attempt_id,p_phase_id,p_binding_nonce,p_device_id,p_game_id);
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 RETURN QUERY SELECT b.tenant_id,b.d5,b.wire_d4,b.internal_generation,
 b.event_fingerprint FROM sync_fence.writer_bindings b
 WHERE (b.tenant_id,b.attempt_id,b.phase_id,b.device_id,b.game_id)=
 (p_tenant_id,p_attempt_id,p_phase_id,p_device_id,p_game_id)
 AND b.state='open' AND b.transaction_id=own_xid
 AND b.expires_at>pg_catalog.clock_timestamp() FOR SHARE;
 IF NOT FOUND THEN
 RAISE EXCEPTION 'P3 binding rejected' USING ERRCODE='42501'; END IF;
END;
$p3_binding$;
ALTER FUNCTION sync_fence_api.read_p3_writer_binding(
 uuid,uuid,uuid,bytea,uuid,uuid) OWNER TO pitchlog_sync_binding_fn_owner;
REVOKE ALL ON FUNCTION sync_fence_api.read_p3_writer_binding(
 uuid,uuid,uuid,bytea,uuid,uuid) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_fence_api.read_p3_writer_binding(
 uuid,uuid,uuid,bytea,uuid,uuid) TO pitchlog_sync_right_fn_owner;
