-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:rg1_api:rg1_assert_open_before_commit(uuid)

CREATE OR REPLACE FUNCTION rg1_api.rg1_assert_open_before_commit(p_tenant_id uuid)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
    tenant_context uuid;
    gate_state text;
BEGIN
    tenant_context := NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid;
    IF tenant_context IS NULL OR p_tenant_id IS DISTINCT FROM tenant_context THEN
        RETURN false;
    END IF;

    SELECT state INTO STRICT gate_state
    FROM public.rg1_restore_gate
    WHERE singleton_id = 1
    FOR SHARE NOWAIT;
    IF gate_state IS DISTINCT FROM 'open' THEN
        RETURN false;
    END IF;
    RETURN rg1_control.controller_lease_alive() IS TRUE;
END;
$function$;
ALTER FUNCTION rg1_api.rg1_assert_open_before_commit(uuid)
    OWNER TO pitchlog_rg1_fn_owner;
REVOKE ALL PRIVILEGES ON FUNCTION rg1_api.rg1_assert_open_before_commit(uuid)
    FROM PUBLIC, pitchlog_app, pitchlog_initial_actor;
GRANT EXECUTE ON FUNCTION rg1_api.rg1_assert_open_before_commit(uuid)
    TO pitchlog_app, pitchlog_initial_actor;
