-- ELEMENT-TYPE: database
-- ELEMENT-ID: current_database

DO $authz$
DECLARE
    database_name TEXT := pg_catalog.current_database();
BEGIN
    EXECUTE pg_catalog.format(
        'ALTER DATABASE %I OWNER TO pitchlog_owner',
        database_name
    );
    EXECUTE pg_catalog.format(
        'REVOKE ALL PRIVILEGES ON DATABASE %I FROM PUBLIC, pitchlog_app, pitchlog_shared_fn_owner, pitchlog_management_fn_owner',
        database_name
    );
    EXECUTE pg_catalog.format(
        'GRANT CONNECT ON DATABASE %I TO pitchlog_app',
        database_name
    );
END;
$authz$;
