-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:initial_right_api:begin_start_attempt(uuid, uuid, uuid, uuid, bytea, uuid)
-- 未適用候補。Python私有actorの資格/phase照合と既issuerを代替しない。
CREATE OR REPLACE FUNCTION initial_right_api.begin_start_attempt(p_tenant_id uuid, p_game_id uuid, p_start_request_id uuid, p_device_id uuid, p_request_digest bytea, p_attempt_id uuid)
RETURNS TABLE(attempt_id uuid, outcome text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path TO pg_catalog, pg_temp
AS $body$
DECLARE v_request record; v_attempt record;
BEGIN
    IF session_user <> 'pitchlog_initial_actor'
       OR current_user <> 'pitchlog_initial_fn_owner'
       OR p_tenant_id IS NULL
       OR NULLIF(pg_catalog.current_setting('app.tenant_id',true),'') IS DISTINCT FROM p_tenant_id::text
       OR p_game_id IS NULL
       OR p_start_request_id IS NULL
       OR p_device_id IS NULL
       OR p_request_digest IS NULL
       OR p_attempt_id IS NULL
       OR pg_catalog.octet_length(p_request_digest)<>32 THEN
        RAISE EXCEPTION 'initial right subject or input rejected' USING ERRCODE='42501';
    END IF;
    -- before-business短intent専用。資格の真照合は同SessionのPython hmacが先行する。
    PERFORM d.device_id FROM public.trusted_devices AS d
     WHERE d.tenant_id=p_tenant_id AND d.device_id=p_device_id AND d.revoked_at IS NULL
     FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE = '23514'; END IF;
    PERFORM g.id FROM public.games AS g WHERE g.tenant_id=p_tenant_id AND g.id=p_game_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE = '23514'; END IF;
    INSERT INTO public.game_start_requests (tenant_id,game_id,start_request_id,device_id,request_digest)
     VALUES (p_tenant_id,p_game_id,p_start_request_id,p_device_id,p_request_digest)
     ON CONFLICT (tenant_id,game_id,start_request_id) DO NOTHING;
    SELECT r.device_id,r.request_digest INTO STRICT v_request FROM public.game_start_requests AS r
     WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id AND r.start_request_id=p_start_request_id
     FOR UPDATE;
    IF v_request.device_id IS DISTINCT FROM p_device_id
     OR v_request.request_digest IS DISTINCT FROM p_request_digest THEN RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE = '23514'; END IF;
    -- 旧rolled_backの再試行許可は別制御差分。期限や0行から新attemptへ進めない。
    BEGIN
        SELECT a.attempt_id,a.outcome INTO STRICT v_attempt FROM public.game_start_attempts AS a
         WHERE a.tenant_id=p_tenant_id AND a.game_id=p_game_id AND a.start_request_id=p_start_request_id
           AND a.device_id=p_device_id LIMIT 2 FOR UPDATE;
    EXCEPTION WHEN no_data_found THEN
        INSERT INTO public.game_start_attempts (tenant_id,attempt_id,game_id,start_request_id,device_id)
         VALUES (p_tenant_id,p_attempt_id,p_game_id,p_start_request_id,p_device_id);
        RETURN QUERY SELECT p_attempt_id,'pending'::text;
        RETURN;
    END;
    IF v_attempt.outcome NOT IN ('pending','committed') THEN RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE = '23514'; END IF;
    RETURN QUERY SELECT v_attempt.attempt_id,v_attempt.outcome;
EXCEPTION WHEN integrity_constraint_violation OR too_many_rows THEN
    -- 制約detailへdigest/暗号文/owner行を露出せず、transactionは失敗のまま返す。
    RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE='23514';
END;
$body$;
ALTER FUNCTION initial_right_api.begin_start_attempt(uuid, uuid, uuid, uuid, bytea, uuid) OWNER TO pitchlog_initial_fn_owner;
REVOKE ALL ON FUNCTION initial_right_api.begin_start_attempt(uuid, uuid, uuid, uuid, bytea, uuid) FROM PUBLIC, pitchlog_app;
GRANT EXECUTE ON FUNCTION initial_right_api.begin_start_attempt(uuid, uuid, uuid, uuid, bytea, uuid) TO pitchlog_initial_actor;
