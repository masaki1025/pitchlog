-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:nonplay_write_admissions:nonplay_update

CREATE POLICY nonplay_update ON sync_fence.nonplay_write_admissions AS PERMISSIVE FOR UPDATE TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app') WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app');
