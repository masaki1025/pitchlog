-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:rg1_control:controller_lease_alive()

CREATE OR REPLACE FUNCTION rg1_control.controller_lease_alive()
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
BEGIN
    -- 一般公開のsession user/database/PIDだけを最新化して使う。
    PERFORM pg_catalog.pg_stat_clear_snapshot();
    RETURN EXISTS (
        SELECT 1 FROM pg_catalog.pg_locks AS open_lock
        JOIN pg_catalog.pg_locks AS controller_lock
          ON controller_lock.pid = open_lock.pid
         AND controller_lock.database = open_lock.database
        JOIN pg_catalog.pg_stat_activity AS backend
          ON backend.pid = open_lock.pid AND backend.datid = open_lock.database
        WHERE open_lock.locktype = 'advisory'
          AND open_lock.database = (
              SELECT oid FROM pg_catalog.pg_database
              WHERE datname = pg_catalog.current_database()
          )
          AND open_lock.classid = 1380397379::oid
          AND open_lock.objid = 2::oid AND open_lock.objsubid = 2
          AND open_lock.mode = 'ExclusiveLock' AND open_lock.granted
          AND controller_lock.locktype = 'advisory'
          AND controller_lock.classid = 1380397379::oid
          AND controller_lock.objid = 1::oid AND controller_lock.objsubid = 2
          AND controller_lock.mode = 'ExclusiveLock' AND controller_lock.granted
          AND backend.usename = 'pitchlog_rg1_control_actor'
    );
END;
$function$;
ALTER FUNCTION rg1_control.controller_lease_alive() OWNER TO pitchlog_rg1_control_owner;
REVOKE ALL PRIVILEGES ON FUNCTION rg1_control.controller_lease_alive() FROM PUBLIC, pitchlog_app;
GRANT EXECUTE ON FUNCTION rg1_control.controller_lease_alive() TO pitchlog_rg1_control_actor;
GRANT EXECUTE ON FUNCTION rg1_control.controller_lease_alive() TO pitchlog_rg1_fn_owner;
