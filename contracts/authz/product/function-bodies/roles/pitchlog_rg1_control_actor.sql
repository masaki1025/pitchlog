-- ELEMENT-TYPE: role
-- ELEMENT-ID: pitchlog_rg1_control_actor

DO $authz$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'pitchlog_rg1_control_actor'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles r
            WHERE r.rolname = 'pitchlog_rg1_control_actor'
              AND NOT r.rolsuper
              AND NOT r.rolbypassrls
              AND r.rolcanlogin
              AND NOT r.rolcreaterole
              AND NOT r.rolcreatedb
              AND NOT r.rolreplication
              AND NOT r.rolinherit
              AND NOT EXISTS (
                  SELECT 1 FROM pg_catalog.pg_auth_members m
                  WHERE m.roleid = r.oid OR m.member = r.oid
              )
        ) THEN
            RAISE EXCEPTION 'lifecycle role collision: pitchlog_rg1_control_actor';
        END IF;
    ELSE
        CREATE ROLE pitchlog_rg1_control_actor WITH
            NOSUPERUSER NOBYPASSRLS LOGIN NOCREATEROLE NOCREATEDB NOREPLICATION NOINHERIT;
    END IF;
END;
$authz$;
