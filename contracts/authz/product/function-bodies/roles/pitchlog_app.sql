-- ELEMENT-TYPE: role
-- ELEMENT-ID: pitchlog_app

DO $authz$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_roles
        WHERE rolname = 'pitchlog_app'
    ) THEN
        CREATE ROLE pitchlog_app;
    END IF;
END;
$authz$;

ALTER ROLE pitchlog_app WITH
    NOSUPERUSER
    NOBYPASSRLS
    LOGIN
    NOCREATEROLE
    NOCREATEDB
    NOREPLICATION
    NOINHERIT;
