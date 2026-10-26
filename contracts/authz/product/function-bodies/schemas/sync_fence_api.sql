-- ELEMENT-TYPE: schema
-- ELEMENT-ID: sync_fence_api

DO $schema_guard$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_namespace n JOIN pg_catalog.pg_roles r ON r.oid=n.nspowner WHERE n.nspname='sync_fence_api' AND r.rolname='pitchlog_sync_binding_fn_owner') THEN
  IF EXISTS(SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname='sync_fence_api') THEN RAISE EXCEPTION 'schema collision: sync_fence_api'; END IF;
  CREATE SCHEMA sync_fence_api AUTHORIZATION pitchlog_sync_binding_fn_owner;
 END IF;
END;$schema_guard$;
REVOKE ALL ON SCHEMA sync_fence_api FROM PUBLIC;
REVOKE CREATE ON SCHEMA sync_fence_api FROM pitchlog_app;
GRANT USAGE ON SCHEMA sync_fence_api TO pitchlog_app;
REVOKE CREATE ON SCHEMA sync_fence_api FROM pitchlog_sync_binding_actor;
GRANT USAGE ON SCHEMA sync_fence_api TO pitchlog_sync_binding_actor;
REVOKE CREATE ON SCHEMA sync_fence_api FROM pitchlog_sync_right_fn_owner;
GRANT USAGE ON SCHEMA sync_fence_api TO pitchlog_sync_right_fn_owner;
