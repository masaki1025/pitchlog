-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:rg1_control:read_closed_gate()

CREATE OR REPLACE FUNCTION rg1_control.read_closed_gate()
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
    gate_state text;
    observed jsonb;
BEGIN
    IF session_user IS DISTINCT FROM 'pitchlog_rg1_control_actor'
       OR pg_catalog.current_setting('transaction_isolation') <> 'read committed'
    THEN
        RAISE EXCEPTION 'RG1 controller identity is not valid' USING ERRCODE = '42501';
    END IF;
    -- 自分/子取引の未commit UPDATEはtop XIDを割当てる。別取引だけを認める。
    -- ロック/UPDATEでXIDを割当てる前の入口で確認し、取得後には再検査しない。
    IF pg_catalog.pg_current_xact_id_if_assigned() IS NOT NULL THEN
        RAISE EXCEPTION 'RG1 close is not committed' USING ERRCODE = '55000';
    END IF;
    PERFORM pg_catalog.pg_stat_clear_snapshot();
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_locks AS controller_lock
        JOIN pg_catalog.pg_stat_activity AS backend
          ON backend.pid = controller_lock.pid
         AND backend.datid = controller_lock.database
        WHERE controller_lock.locktype = 'advisory'
          AND controller_lock.database = (
              SELECT oid FROM pg_catalog.pg_database
              WHERE datname = pg_catalog.current_database()
          )
          AND controller_lock.classid = 1380397379::oid
          AND controller_lock.objid = 1::oid
          AND controller_lock.objsubid = 2
          AND controller_lock.mode = 'ExclusiveLock'
          AND controller_lock.granted
          AND controller_lock.pid = pg_catalog.pg_backend_pid()
          AND backend.usename = 'pitchlog_rg1_control_actor'
    ) THEN
        RAISE EXCEPTION 'RG1 controller lease is not held' USING ERRCODE = '55000';
    END IF;
    SELECT state INTO STRICT gate_state FROM public.rg1_restore_gate
    WHERE singleton_id = 1;
    IF gate_state <> 'closed' THEN
        RAISE EXCEPTION 'RG1 gate is not closed' USING ERRCODE = '55000';
    END IF;
    SELECT pg_catalog.jsonb_build_object(
        'system_identifier', control.system_identifier::text,
        'database_oid', database.oid::bigint,
        'database_name', database.datname::text,
        'postmaster_started_at', pg_catalog.to_char(
            pg_catalog.pg_postmaster_start_time() AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
        ),
        'backend_pid', pg_catalog.pg_backend_pid(),
        'gate_state', gate_state
    ) INTO STRICT observed
    FROM pg_catalog.pg_control_system() AS control
    CROSS JOIN pg_catalog.pg_database AS database
    WHERE database.datname = pg_catalog.current_database();
    RETURN observed;
END;
$function$;
ALTER FUNCTION rg1_control.read_closed_gate() OWNER TO pitchlog_rg1_control_owner;
REVOKE ALL PRIVILEGES ON FUNCTION rg1_control.read_closed_gate() FROM PUBLIC, pitchlog_app;
GRANT EXECUTE ON FUNCTION rg1_control.read_closed_gate() TO pitchlog_rg1_control_actor;
