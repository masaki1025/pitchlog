-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:initial_right_api:lookup_existing_start_attempt(uuid, uuid, uuid, uuid, bytea)

CREATE OR REPLACE FUNCTION initial_right_api.lookup_existing_start_attempt(
    p_tenant_id uuid, p_game_id uuid, p_start_request_id uuid,
    p_device_id uuid, p_request_digest bytea)
RETURNS TABLE(attempt_id uuid, outcome text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path TO pg_catalog, pg_temp
AS $body$
DECLARE req record; attempt record;
BEGIN
    IF session_user <> 'pitchlog_initial_actor'
       OR current_user <> 'pitchlog_initial_fn_owner'
       OR p_tenant_id IS NULL OR p_game_id IS NULL
       OR p_start_request_id IS NULL OR p_device_id IS NULL
       OR p_request_digest IS NULL
       OR pg_catalog.octet_length(p_request_digest) <> 32
       OR NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')
          IS DISTINCT FROM p_tenant_id::text THEN
        RAISE EXCEPTION 'initial lookup subject rejected' USING ERRCODE='42501';
    END IF;
    SELECT r.device_id,r.request_digest INTO req
      FROM public.game_start_requests r
      WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id
        AND r.start_request_id=p_start_request_id FOR UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    IF req.device_id IS DISTINCT FROM p_device_id
       OR req.request_digest IS DISTINCT FROM p_request_digest THEN
        RAISE EXCEPTION 'initial lookup owner rejected' USING ERRCODE='42501';
    END IF;
    BEGIN
        SELECT a.attempt_id,a.outcome INTO STRICT attempt
          FROM public.game_start_attempts a
          WHERE a.tenant_id=p_tenant_id AND a.game_id=p_game_id
            AND a.start_request_id=p_start_request_id AND a.device_id=p_device_id
          LIMIT 2 FOR UPDATE;
    EXCEPTION WHEN no_data_found THEN RETURN;
    END;
    IF attempt.outcome NOT IN ('pending','committed') THEN
        RAISE EXCEPTION 'initial lookup remains unresolved' USING ERRCODE='42501';
    END IF;
    RETURN QUERY SELECT attempt.attempt_id,attempt.outcome;
EXCEPTION WHEN integrity_constraint_violation OR too_many_rows THEN
    RAISE EXCEPTION 'initial lookup rejected' USING ERRCODE='23514';
END;
$body$;
ALTER FUNCTION initial_right_api.lookup_existing_start_attempt(
    uuid, uuid, uuid, uuid, bytea) OWNER TO pitchlog_initial_fn_owner;
REVOKE EXECUTE ON FUNCTION initial_right_api.lookup_existing_start_attempt(
    uuid, uuid, uuid, uuid, bytea)
    FROM PUBLIC, pitchlog_app, pitchlog_initial_auth_verifier;
GRANT EXECUTE ON FUNCTION initial_right_api.lookup_existing_start_attempt(
    uuid, uuid, uuid, uuid, bytea) TO pitchlog_initial_actor;
