-- 業務表/既存appへ権限を広げない、authority専用のread-only観測。
-- builtin既定PUBLIC EXECUTEは変更しない。以下は追加の明示GRANTだけを限定する。
CREATE ROLE pitchlog_ledger_identity_owner NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE pitchlog_ledger_identity_probe LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
-- 正規製品DDLがPUBLICのCONNECTを剥奪するため、観測subjectだけへCONNECTを追加する。
DO $$ BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO pitchlog_ledger_identity_probe', current_database());
END $$;
CREATE SCHEMA pitchlog_ledger_observer AUTHORIZATION pitchlog_ledger_identity_owner;
REVOKE ALL ON SCHEMA pitchlog_ledger_observer FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO pitchlog_ledger_identity_owner;
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
REVOKE ALL ON FUNCTION pitchlog_ledger_observer.identity() FROM PUBLIC;
GRANT USAGE ON SCHEMA pitchlog_ledger_observer TO pitchlog_ledger_identity_probe;
GRANT EXECUTE ON FUNCTION pitchlog_ledger_observer.identity() TO pitchlog_ledger_identity_probe;
