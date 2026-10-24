-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:pitchlog_ledger_observer:identity()

CREATE FUNCTION pitchlog_ledger_observer.identity() RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
SELECT jsonb_build_object(
    'system_id', (SELECT system_identifier::text FROM pg_control_system()),
    'database', current_database(), 'started_at', pg_postmaster_start_time()::text,
    'version', current_setting('server_version_num')::integer,
    'recovery', pg_is_in_recovery()
)
$$;
ALTER FUNCTION pitchlog_ledger_observer.identity() OWNER TO pitchlog_ledger_identity_owner;
REVOKE ALL PRIVILEGES ON FUNCTION pitchlog_ledger_observer.identity() FROM PUBLIC, pitchlog_app;
GRANT EXECUTE ON FUNCTION pitchlog_ledger_observer.identity() TO pitchlog_ledger_identity_probe;
