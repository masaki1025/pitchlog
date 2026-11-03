-- ELEMENT-TYPE: schema
-- ELEMENT-ID: sync_fence

DO $schema_guard$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_namespace n JOIN pg_catalog.pg_roles r ON r.oid=n.nspowner WHERE n.nspname='sync_fence' AND r.rolname='pitchlog_owner') THEN
  RAISE EXCEPTION 'migration schema missing or wrong owner: sync_fence';
 END IF;
END;$schema_guard$;
REVOKE ALL ON SCHEMA sync_fence FROM PUBLIC;
REVOKE CREATE ON SCHEMA sync_fence FROM pitchlog_sync_binding_fn_owner;
GRANT USAGE ON SCHEMA sync_fence TO pitchlog_sync_binding_fn_owner;
GRANT USAGE ON SCHEMA sync_fence TO pitchlog_sync_right_fn_owner;
