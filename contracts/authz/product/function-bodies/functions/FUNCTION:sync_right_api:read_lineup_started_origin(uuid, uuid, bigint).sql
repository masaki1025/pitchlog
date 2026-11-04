-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:read_lineup_started_origin(uuid, uuid, bigint)

CREATE FUNCTION sync_right_api.read_lineup_started_origin(
p_tenant_id uuid,p_game_id uuid,p_generation bigint)
RETURNS TABLE(record_json text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $origin$
DECLARE origins jsonb;
BEGIN
 IF session_user IS DISTINCT FROM 'pitchlog_app'
 OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR p_game_id IS NULL OR p_generation IS NULL OR p_generation<=0 THEN RAISE EXCEPTION 'play prefix admission rejected' USING ERRCODE='42501'; END IF;
 SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(x)) INTO origins FROM (
 SELECT DISTINCT r.start_request_id::text AS start_request_id,
 r.device_id::text AS device_id
 FROM public.game_start_requests r JOIN public.game_start_attempts a
 ON (a.tenant_id,a.game_id,a.start_request_id,a.device_id)=
 (r.tenant_id,r.game_id,r.start_request_id,r.device_id)
 WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id AND a.outcome='committed'
 LIMIT 2) x;
 IF origins IS NULL OR pg_catalog.jsonb_array_length(origins)<>1 THEN RAISE EXCEPTION 'play prefix admission rejected' USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT (origins->0)::text;
END;
$origin$;

ALTER FUNCTION sync_right_api.read_lineup_started_origin(uuid, uuid, bigint) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.read_lineup_started_origin(uuid, uuid, bigint) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_right_api.read_lineup_started_origin(uuid, uuid, bigint) TO pitchlog_app;
