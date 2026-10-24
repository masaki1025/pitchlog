-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:rg1_control:bind_initial_fresh_epoch(bigint)

CREATE FUNCTION rg1_control.bind_initial_fresh_epoch(p_recovery_generation bigint)
RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
    gate_state text;
    bound_epoch bigint;
    changed bigint;
BEGIN
    IF session_user IS DISTINCT FROM 'pitchlog_rg1_control_actor'
       OR pg_catalog.current_setting('transaction_isolation') <> 'read committed'
       OR p_recovery_generation IS DISTINCT FROM 1::bigint
       OR pg_catalog.pg_current_xact_id_if_assigned() IS NOT NULL THEN
        RETURN false;
    END IF;
    PERFORM pg_catalog.pg_stat_clear_snapshot();
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_locks AS held
        JOIN pg_catalog.pg_stat_activity AS backend
          ON backend.pid = held.pid AND backend.datid = held.database
        WHERE held.locktype = 'advisory'
          AND held.database = (
              SELECT oid FROM pg_catalog.pg_database
              WHERE datname = pg_catalog.current_database())
          AND held.classid = 1380397379::oid AND held.objid = 1::oid
          AND held.objsubid = 2 AND held.mode = 'ExclusiveLock' AND held.granted
          AND held.pid = pg_catalog.pg_backend_pid()
          AND backend.usename = 'pitchlog_rg1_control_actor'
    ) THEN
        RETURN false;
    END IF;
    SELECT state, recovery_generation INTO STRICT gate_state, bound_epoch
      FROM public.rg1_restore_gate WHERE singleton_id = 1 FOR UPDATE;
    IF gate_state <> 'closed' OR bound_epoch IS NOT NULL THEN
        RETURN false;
    END IF;
    UPDATE public.rg1_restore_gate
       SET recovery_generation = p_recovery_generation
     WHERE singleton_id = 1;
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed = 1;
END;
$function$;
ALTER FUNCTION rg1_control.bind_initial_fresh_epoch(bigint) OWNER TO pitchlog_rg1_control_owner;
REVOKE ALL PRIVILEGES ON FUNCTION rg1_control.bind_initial_fresh_epoch(bigint) FROM PUBLIC, pitchlog_app;
GRANT EXECUTE ON FUNCTION rg1_control.bind_initial_fresh_epoch(bigint) TO pitchlog_rg1_control_actor;
