-- ELEMENT-TYPE: schema
-- ELEMENT-ID: stats_basic_api

DO $stats_basic_schema$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_namespace n
  JOIN pg_catalog.pg_roles r ON r.oid=n.nspowner
  WHERE n.nspname='stats_basic_api' AND r.rolname='pitchlog_owner') THEN
  IF EXISTS(SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname='stats_basic_api') THEN
   RAISE EXCEPTION 'basic stats schema owner collision';
  END IF;
  CREATE SCHEMA stats_basic_api AUTHORIZATION pitchlog_owner;
 END IF;
END;$stats_basic_schema$;
REVOKE ALL ON SCHEMA stats_basic_api FROM PUBLIC;
REVOKE CREATE ON SCHEMA stats_basic_api FROM pitchlog_app,pitchlog_sync_right_fn_owner;
GRANT USAGE ON SCHEMA stats_basic_api TO pitchlog_app,pitchlog_sync_right_fn_owner;
