-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:lifecycle_write_admissions:lifecycle_insert

CREATE POLICY lifecycle_insert ON sync_fence.lifecycle_write_admissions AS PERMISSIVE FOR INSERT TO pitchlog_sync_right_fn_owner WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app' AND transaction_id=pg_catalog.pg_current_xact_id()::text);
