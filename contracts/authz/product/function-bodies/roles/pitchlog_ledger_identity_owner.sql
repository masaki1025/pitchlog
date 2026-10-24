-- ELEMENT-TYPE: role
-- ELEMENT-ID: pitchlog_ledger_identity_owner

DO $authz$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'pitchlog_ledger_identity_owner'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles r
            WHERE r.rolname = 'pitchlog_ledger_identity_owner'
              AND NOT r.rolsuper
              AND NOT r.rolbypassrls
              AND NOT r.rolcanlogin
              AND NOT r.rolcreaterole
              AND NOT r.rolcreatedb
              AND NOT r.rolreplication
              AND r.rolinherit
              AND NOT EXISTS (
                  SELECT 1 FROM pg_catalog.pg_auth_members m
                  WHERE m.roleid = r.oid OR m.member = r.oid
              )
        ) THEN
            RAISE EXCEPTION 'lifecycle role collision: pitchlog_ledger_identity_owner';
        END IF;
    ELSE
        CREATE ROLE pitchlog_ledger_identity_owner WITH
            NOSUPERUSER NOBYPASSRLS NOLOGIN NOCREATEROLE NOCREATEDB NOREPLICATION INHERIT;
    END IF;
END;
$authz$;
