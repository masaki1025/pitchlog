-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:rg1_control:scope_binding(uuid)

CREATE OR REPLACE FUNCTION rg1_control.scope_binding(p_tenant_id uuid)
RETURNS text
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
    tenant_context uuid;
    observed text;
BEGIN
    IF session_user NOT IN ('pitchlog_app', 'pitchlog_initial_actor') THEN
        RAISE EXCEPTION 'RG1 scope actor mismatch' USING ERRCODE = '42501';
    END IF;
    tenant_context := NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid;
    IF tenant_context IS NULL OR p_tenant_id IS DISTINCT FROM tenant_context THEN
        RAISE EXCEPTION 'RG1 tenant binding mismatch' USING ERRCODE = '42501';
    END IF;
    SELECT pg_catalog.jsonb_build_object(
        'system_identifier', control.system_identifier::text,
        'database_oid', database.oid::bigint,
        'database_name', database.datname::text,
        'postmaster_started_at', pg_catalog.to_char(
            pg_catalog.pg_postmaster_start_time() AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
        ),
        'backend_pid', pg_catalog.pg_backend_pid()
    )::text INTO STRICT observed
    FROM pg_catalog.pg_control_system() AS control
    CROSS JOIN pg_catalog.pg_database AS database
    WHERE database.datname = pg_catalog.current_database();
    RETURN observed;
END;
$function$;
ALTER FUNCTION rg1_control.scope_binding(uuid) OWNER TO pitchlog_rg1_control_owner;
REVOKE ALL PRIVILEGES ON FUNCTION rg1_control.scope_binding(uuid) FROM PUBLIC, pitchlog_app;
GRANT EXECUTE ON FUNCTION rg1_control.scope_binding(uuid) TO pitchlog_app;
GRANT EXECUTE ON FUNCTION rg1_control.scope_binding(uuid) TO pitchlog_initial_actor;
