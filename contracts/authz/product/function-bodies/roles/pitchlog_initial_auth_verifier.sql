-- ELEMENT-TYPE: role
-- ELEMENT-ID: pitchlog_initial_auth_verifier

DO $authz$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'pitchlog_initial_auth_verifier'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles r
            WHERE r.rolname = 'pitchlog_initial_auth_verifier'
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
            RAISE EXCEPTION 'lifecycle role collision: pitchlog_initial_auth_verifier';
        END IF;
    ELSE
        CREATE ROLE pitchlog_initial_auth_verifier WITH
            NOSUPERUSER NOBYPASSRLS LOGIN NOCREATEROLE NOCREATEDB NOREPLICATION NOINHERIT;
    END IF;
END;
$authz$;
