-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:nonplay_write_admissions:nonplay_select

CREATE POLICY nonplay_select ON sync_fence.nonplay_write_admissions AS PERMISSIVE FOR SELECT TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app');
