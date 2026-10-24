-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:rg1_control:try_controller_lease()

CREATE OR REPLACE FUNCTION rg1_control.try_controller_lease()
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
BEGIN
    IF session_user IS DISTINCT FROM 'pitchlog_rg1_control_actor'
       OR pg_catalog.current_setting('transaction_isolation') <> 'read committed'
    THEN
        RETURN false;
    END IF;
    PERFORM pg_catalog.pg_stat_clear_snapshot();
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_stat_activity AS backend
        WHERE backend.pid = pg_catalog.pg_backend_pid()
          AND backend.datid = (
              SELECT oid FROM pg_catalog.pg_database
              WHERE datname = pg_catalog.current_database()
          )
          AND backend.usename = 'pitchlog_rg1_control_actor'
    ) THEN
        RETURN false;
    END IF;
    -- 再入時にpg_try_advisory_lockを呼ばず、session lockcountを増やさない。
    IF EXISTS (
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
        RETURN true;
    END IF;
    RETURN pg_catalog.pg_try_advisory_lock(1380397379, 1);
END;
$function$;
ALTER FUNCTION rg1_control.try_controller_lease() OWNER TO pitchlog_rg1_control_owner;
REVOKE ALL PRIVILEGES ON FUNCTION rg1_control.try_controller_lease() FROM PUBLIC, pitchlog_app;
GRANT EXECUTE ON FUNCTION rg1_control.try_controller_lease() TO pitchlog_rg1_control_actor;
