-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:rg1_control:release_controller_lease()

CREATE OR REPLACE FUNCTION rg1_control.release_controller_lease()
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
    gate_state text;
BEGIN
    IF session_user IS DISTINCT FROM 'pitchlog_rg1_control_actor'
       OR pg_catalog.current_setting('transaction_isolation') <> 'read committed'
    THEN
        RETURN false;
    END IF;
    -- 自分/子取引の未commit UPDATEはtop XIDを割当てる。別取引だけを認める。
    -- ロック/UPDATEでXIDを割当てる前の入口で確認し、取得後には再検査しない。
    IF pg_catalog.pg_current_xact_id_if_assigned() IS NOT NULL THEN
        RETURN false;
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
        RETURN false;
    END IF;
    SELECT state INTO STRICT gate_state FROM public.rg1_restore_gate
    WHERE singleton_id = 1;
    IF gate_state <> 'closed' THEN
        RETURN false;
    END IF;
    -- close commit後にopen→controllerの順。積み増された別のlockは誤解放しない。
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_locks AS open_lock
        WHERE open_lock.locktype = 'advisory'
          AND open_lock.database = (
              SELECT oid FROM pg_catalog.pg_database
              WHERE datname = pg_catalog.current_database()
          )
          AND open_lock.classid = 1380397379::oid
          AND open_lock.objid = 2::oid
          AND open_lock.objsubid = 2
          AND open_lock.mode = 'ExclusiveLock'
          AND open_lock.granted
          AND open_lock.pid = pg_catalog.pg_backend_pid()
    ) THEN
        IF NOT pg_catalog.pg_advisory_unlock(1380397379, 2) THEN
            RETURN false;
        END IF;
        IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_locks AS open_lock
        WHERE open_lock.locktype = 'advisory'
          AND open_lock.database = (
              SELECT oid FROM pg_catalog.pg_database
              WHERE datname = pg_catalog.current_database()
          )
          AND open_lock.classid = 1380397379::oid
          AND open_lock.objid = 2::oid
          AND open_lock.objsubid = 2
          AND open_lock.mode = 'ExclusiveLock'
          AND open_lock.granted
          AND open_lock.pid = pg_catalog.pg_backend_pid()
    ) THEN
            RETURN false;
        END IF;
    END IF;
    IF NOT pg_catalog.pg_advisory_unlock(1380397379, 1) THEN
        RETURN false;
    END IF;
    RETURN NOT EXISTS (
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
    );
END;
$function$;
ALTER FUNCTION rg1_control.release_controller_lease() OWNER TO pitchlog_rg1_control_owner;
REVOKE ALL PRIVILEGES ON FUNCTION rg1_control.release_controller_lease() FROM PUBLIC, pitchlog_app;
GRANT EXECUTE ON FUNCTION rg1_control.release_controller_lease() TO pitchlog_rg1_control_actor;
