-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:lifecycle_write_admissions:lifecycle_update

CREATE POLICY lifecycle_update ON sync_fence.lifecycle_write_admissions AS PERMISSIVE FOR UPDATE TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app' AND transaction_id=pg_catalog.pg_current_xact_id()::text) WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app' AND transaction_id=pg_catalog.pg_current_xact_id()::text);
