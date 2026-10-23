-- RG1制限ライフサイクル。実fresh証明はpeer controllerのDurableLedgerが所有する。
-- advisory 2-int専用namespace 0x52473143 (RG1C) = 1380397379。
-- controller mutex=(1380397379,1)、open生存lease=(1380397379,2)、objsubid=2。
-- 旧open行だけ/別DB/app同keyは生存証明にならない。全域fence/epochを発行しない。
-- 既存製品DBのPUBLIC CONNECT/TEMP取消済みprofileを前提とする。

CREATE ROLE pitchlog_rg1_control_owner NOLOGIN NOSUPERUSER NOBYPASSRLS
    NOINHERIT NOCREATEROLE NOCREATEDB NOREPLICATION;
CREATE ROLE pitchlog_rg1_control_actor LOGIN NOSUPERUSER NOBYPASSRLS
    NOINHERIT NOCREATEROLE NOCREATEDB NOREPLICATION;
CREATE SCHEMA rg1_control AUTHORIZATION pitchlog_rg1_control_owner;
REVOKE ALL PRIVILEGES ON SCHEMA rg1_control FROM PUBLIC;
GRANT USAGE ON SCHEMA rg1_control
    TO pitchlog_rg1_control_actor, pitchlog_rg1_fn_owner, pitchlog_app;
GRANT USAGE ON SCHEMA public TO pitchlog_rg1_control_owner;

DO $database_acl$
BEGIN
    EXECUTE pg_catalog.format(
        'GRANT CONNECT ON DATABASE %I TO pitchlog_rg1_control_actor',
        pg_catalog.current_database()
    );
    EXECUTE pg_catalog.format(
        'REVOKE CREATE, TEMPORARY ON DATABASE %I FROM pitchlog_rg1_control_actor',
        pg_catalog.current_database()
    );
    IF pg_catalog.has_database_privilege(
        'pitchlog_rg1_control_actor', pg_catalog.current_database(), 'TEMPORARY'
    ) OR pg_catalog.has_database_privilege(
        'pitchlog_rg1_control_actor', pg_catalog.current_database(), 'CREATE'
    ) THEN
        RAISE EXCEPTION 'RG1 actor database profile is not restricted'
            USING ERRCODE = '42501';
    END IF;
END;
$database_acl$;

GRANT SELECT (singleton_id, state), UPDATE (state)
    ON TABLE public.rg1_restore_gate TO pitchlog_rg1_control_owner;
ALTER TABLE public.rg1_restore_gate ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rg1_restore_gate FORCE ROW LEVEL SECURITY;
CREATE POLICY rg1_control_select_singleton ON public.rg1_restore_gate
    FOR SELECT TO pitchlog_rg1_control_owner USING (singleton_id = 1);
CREATE POLICY rg1_control_update_singleton ON public.rg1_restore_gate
    FOR UPDATE TO pitchlog_rg1_control_owner
    USING (singleton_id = 1) WITH CHECK (singleton_id = 1);
-- PUBLICのbuiltin ACLは変更せず、既定非公開環境でもこのownerだけへ与える。
GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system()
    TO pitchlog_rg1_control_owner;


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
ALTER FUNCTION rg1_control.try_controller_lease()
    OWNER TO pitchlog_rg1_control_owner;
REVOKE ALL PRIVILEGES ON FUNCTION rg1_control.try_controller_lease()
    FROM PUBLIC, pitchlog_app, pitchlog_rg1_control_actor, pitchlog_rg1_fn_owner;
GRANT EXECUTE ON FUNCTION rg1_control.try_controller_lease()
    TO pitchlog_rg1_control_actor;


CREATE OR REPLACE FUNCTION rg1_control.close_gate()
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
    changed bigint;
BEGIN
    IF session_user IS DISTINCT FROM 'pitchlog_rg1_control_actor'
       OR pg_catalog.current_setting('transaction_isolation') <> 'read committed'
    THEN
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
    -- この1行の排他更新で既存share writerを排出する。game lockを待たない。
    UPDATE public.rg1_restore_gate SET state = 'closed' WHERE singleton_id = 1;
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed = 1;
END;
$function$;
ALTER FUNCTION rg1_control.close_gate()
    OWNER TO pitchlog_rg1_control_owner;
REVOKE ALL PRIVILEGES ON FUNCTION rg1_control.close_gate()
    FROM PUBLIC, pitchlog_app, pitchlog_rg1_control_actor, pitchlog_rg1_fn_owner;
GRANT EXECUTE ON FUNCTION rg1_control.close_gate()
    TO pitchlog_rg1_control_actor;


CREATE OR REPLACE FUNCTION rg1_control.open_fresh_gate()
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
    gate_state text;
    changed bigint;
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
    WHERE singleton_id = 1 FOR UPDATE;
    IF gate_state <> 'closed' THEN
        RETURN false;
    END IF;
    -- freshは実DurableLedger照合済みの専用peer actorだけが指示する。
    IF NOT EXISTS (
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
        IF NOT pg_catalog.pg_try_advisory_lock(1380397379, 2) THEN
            RETURN false;
        END IF;
    END IF;
    UPDATE public.rg1_restore_gate SET state = 'open' WHERE singleton_id = 1;
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed = 1;
END;
$function$;
ALTER FUNCTION rg1_control.open_fresh_gate()
    OWNER TO pitchlog_rg1_control_owner;
REVOKE ALL PRIVILEGES ON FUNCTION rg1_control.open_fresh_gate()
    FROM PUBLIC, pitchlog_app, pitchlog_rg1_control_actor, pitchlog_rg1_fn_owner;
GRANT EXECUTE ON FUNCTION rg1_control.open_fresh_gate()
    TO pitchlog_rg1_control_actor;


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
ALTER FUNCTION rg1_control.release_controller_lease()
    OWNER TO pitchlog_rg1_control_owner;
REVOKE ALL PRIVILEGES ON FUNCTION rg1_control.release_controller_lease()
    FROM PUBLIC, pitchlog_app, pitchlog_rg1_control_actor, pitchlog_rg1_fn_owner;
GRANT EXECUTE ON FUNCTION rg1_control.release_controller_lease()
    TO pitchlog_rg1_control_actor;


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
ALTER FUNCTION rg1_control.controller_lease_alive()
    OWNER TO pitchlog_rg1_control_owner;
REVOKE ALL PRIVILEGES ON FUNCTION rg1_control.controller_lease_alive()
    FROM PUBLIC, pitchlog_app, pitchlog_rg1_control_actor, pitchlog_rg1_fn_owner;
GRANT EXECUTE ON FUNCTION rg1_control.controller_lease_alive()
    TO pitchlog_rg1_control_actor;
GRANT EXECUTE ON FUNCTION rg1_control.controller_lease_alive()
    TO pitchlog_rg1_fn_owner;


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
ALTER FUNCTION rg1_control.read_closed_gate()
    OWNER TO pitchlog_rg1_control_owner;
REVOKE ALL PRIVILEGES ON FUNCTION rg1_control.read_closed_gate()
    FROM PUBLIC, pitchlog_app, pitchlog_rg1_control_actor, pitchlog_rg1_fn_owner;
GRANT EXECUTE ON FUNCTION rg1_control.read_closed_gate()
    TO pitchlog_rg1_control_actor;


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
ALTER FUNCTION rg1_control.scope_binding(uuid)
    OWNER TO pitchlog_rg1_control_owner;
REVOKE ALL PRIVILEGES ON FUNCTION rg1_control.scope_binding(uuid)
    FROM PUBLIC, pitchlog_app, pitchlog_rg1_control_actor, pitchlog_rg1_fn_owner;
GRANT EXECUTE ON FUNCTION rg1_control.scope_binding(uuid)
    TO pitchlog_app;
