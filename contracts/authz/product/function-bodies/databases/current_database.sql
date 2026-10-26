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
    EXECUTE pg_catalog.format('REVOKE CREATE, TEMPORARY ON DATABASE %I FROM pitchlog_rg1_control_actor', database_name);
    EXECUTE pg_catalog.format('GRANT CONNECT ON DATABASE %I TO pitchlog_rg1_control_actor', database_name);
    EXECUTE pg_catalog.format('REVOKE CREATE, TEMPORARY ON DATABASE %I FROM pitchlog_ledger_identity_probe', database_name);
    EXECUTE pg_catalog.format('GRANT CONNECT ON DATABASE %I TO pitchlog_ledger_identity_probe', database_name);
    EXECUTE pg_catalog.format('REVOKE CREATE, TEMPORARY ON DATABASE %I FROM pitchlog_initial_actor', database_name);
    EXECUTE pg_catalog.format('GRANT CONNECT ON DATABASE %I TO pitchlog_initial_actor', database_name);
END;
$authz$;
DO $authz$ BEGIN EXECUTE pg_catalog.format('GRANT CONNECT ON DATABASE %I TO pitchlog_initial_auth_verifier', pg_catalog.current_database()); EXECUTE pg_catalog.format('REVOKE CREATE, TEMPORARY ON DATABASE %I FROM pitchlog_initial_auth_verifier', pg_catalog.current_database()); END; $authz$;
