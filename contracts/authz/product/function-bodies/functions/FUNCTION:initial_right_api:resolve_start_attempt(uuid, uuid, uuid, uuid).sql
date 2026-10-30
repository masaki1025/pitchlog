-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:initial_right_api:resolve_start_attempt(uuid, uuid, uuid, uuid)
-- 未適用候補。Python私有actorの資格/phase照合と既issuerを代替しない。
CREATE OR REPLACE FUNCTION initial_right_api.resolve_start_attempt(p_tenant_id uuid, p_game_id uuid, p_start_request_id uuid, p_attempt_id uuid)
RETURNS TABLE(outcome text, generation bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path TO pg_catalog, pg_temp
AS $body$
DECLARE v_device uuid; v_outcome text; v_row record;
BEGIN
    IF session_user <> 'pitchlog_initial_actor'
       OR current_user <> 'pitchlog_initial_fn_owner'
       OR p_tenant_id IS NULL
       OR NULLIF(pg_catalog.current_setting('app.tenant_id',true),'') IS DISTINCT FROM p_tenant_id::text
       OR p_game_id IS NULL
       OR p_start_request_id IS NULL
       OR p_attempt_id IS NULL THEN
        RAISE EXCEPTION 'initial right subject or input rejected' USING ERRCODE='42501';
    END IF;
    -- device資格真照合の後、reserve/claimより前。同じbusiness Sessionで保持する。
    SELECT r.device_id INTO v_device FROM public.game_start_requests AS r
     WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id AND r.start_request_id=p_start_request_id
     FOR UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    SELECT a.outcome INTO v_outcome FROM public.game_start_attempts AS a
     WHERE a.tenant_id=p_tenant_id AND a.attempt_id=p_attempt_id AND a.game_id=p_game_id
       AND a.start_request_id=p_start_request_id AND a.device_id=v_device FOR UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    IF v_outcome='pending' THEN
        IF EXISTS (SELECT 1 FROM public.recording_right_deliveries AS d
           WHERE d.tenant_id=p_tenant_id AND d.game_id=p_game_id AND d.start_request_id=p_start_request_id)
        THEN RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE = '23514'; END IF;
        RETURN QUERY SELECT 'pending'::text,NULL::bigint;
    ELSIF v_outcome='committed' THEN
        BEGIN
            SELECT r.* INTO STRICT v_row
              FROM initial_right_api.read_existing_start(p_tenant_id,p_game_id,p_start_request_id) AS r;
        EXCEPTION WHEN no_data_found THEN RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE = '23514';
        END;
        IF v_row.device_id IS DISTINCT FROM v_device THEN RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE = '23514'; END IF;
        RETURN QUERY SELECT 'committed'::text,v_row.generation;
    ELSE
        RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE = '23514';
    END IF;
EXCEPTION WHEN integrity_constraint_violation OR too_many_rows THEN
    -- 制約detailへdigest/暗号文/owner行を露出せず、transactionは失敗のまま返す。
    RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE='23514';
END;
$body$;
ALTER FUNCTION initial_right_api.resolve_start_attempt(uuid, uuid, uuid, uuid) OWNER TO pitchlog_initial_fn_owner;
REVOKE ALL ON FUNCTION initial_right_api.resolve_start_attempt(uuid, uuid, uuid, uuid) FROM PUBLIC, pitchlog_app;
GRANT EXECUTE ON FUNCTION initial_right_api.resolve_start_attempt(uuid, uuid, uuid, uuid) TO pitchlog_initial_actor;
