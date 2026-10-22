-- ELEMENT-TYPE: role
-- ELEMENT-ID: pitchlog_rule_resolution_fn_owner

DO $authz$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'pitchlog_rule_resolution_fn_owner'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles r
            WHERE r.rolname = 'pitchlog_rule_resolution_fn_owner'
              AND NOT r.rolsuper AND r.rolbypassrls AND NOT r.rolcanlogin
              AND NOT r.rolcreaterole AND NOT r.rolcreatedb
              AND NOT r.rolreplication AND NOT r.rolinherit
              AND NOT EXISTS (
                  SELECT 1 FROM pg_catalog.pg_auth_members m
                  WHERE m.roleid = r.oid OR m.member = r.oid
              )
        ) THEN
            RAISE EXCEPTION 'rule owner role collision';
        END IF;
    ELSE
        CREATE ROLE pitchlog_rule_resolution_fn_owner WITH
            NOSUPERUSER BYPASSRLS NOLOGIN NOCREATEROLE NOCREATEDB
            NOREPLICATION NOINHERIT;
    END IF;
END;
$authz$;
