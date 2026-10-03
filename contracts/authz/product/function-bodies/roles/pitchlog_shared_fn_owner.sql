-- ELEMENT-TYPE: role
-- ELEMENT-ID: pitchlog_shared_fn_owner

DO $authz$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_roles
        WHERE rolname = 'pitchlog_shared_fn_owner'
    ) THEN
        CREATE ROLE pitchlog_shared_fn_owner;
    END IF;
END;
$authz$;

ALTER ROLE pitchlog_shared_fn_owner WITH
    NOSUPERUSER
    BYPASSRLS
    NOLOGIN
    NOCREATEROLE
    NOCREATEDB
    NOREPLICATION
    NOINHERIT;
