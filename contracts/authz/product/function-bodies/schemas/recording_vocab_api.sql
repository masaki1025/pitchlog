-- ELEMENT-TYPE: schema
-- ELEMENT-ID: recording_vocab_api

DO $recording_vocab_schema$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_namespace n
  JOIN pg_catalog.pg_roles r ON r.oid=n.nspowner
  WHERE n.nspname='recording_vocab_api' AND r.rolname='pitchlog_recording_vocab_fn_owner') THEN
  IF EXISTS(SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname='recording_vocab_api') THEN
   RAISE EXCEPTION 'recording vocabulary schema collision';
  END IF;
  CREATE SCHEMA recording_vocab_api AUTHORIZATION pitchlog_recording_vocab_fn_owner;
 END IF;
END;$recording_vocab_schema$;
REVOKE ALL ON SCHEMA recording_vocab_api FROM PUBLIC;
REVOKE CREATE ON SCHEMA recording_vocab_api FROM pitchlog_app;
GRANT USAGE ON SCHEMA recording_vocab_api TO pitchlog_app;
