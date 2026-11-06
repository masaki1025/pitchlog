-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:lifecycle_write_admissions:lifecycle_select

CREATE POLICY lifecycle_select ON sync_fence.lifecycle_write_admissions AS PERMISSIVE FOR SELECT TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app');
