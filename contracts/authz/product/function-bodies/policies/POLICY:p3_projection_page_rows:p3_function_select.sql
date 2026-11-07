-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:p3_projection_page_rows:p3_function_select

CREATE POLICY p3_function_select ON sync_fence.p3_projection_page_rows AS PERMISSIVE FOR SELECT TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app');
