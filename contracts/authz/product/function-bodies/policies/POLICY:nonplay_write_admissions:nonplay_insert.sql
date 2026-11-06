-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:nonplay_write_admissions:nonplay_insert

CREATE POLICY nonplay_insert ON sync_fence.nonplay_write_admissions AS PERMISSIVE FOR INSERT TO pitchlog_sync_right_fn_owner WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app');
