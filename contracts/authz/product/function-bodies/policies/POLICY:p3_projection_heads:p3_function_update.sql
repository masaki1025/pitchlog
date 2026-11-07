-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:p3_projection_heads:p3_function_update

CREATE POLICY p3_function_update ON sync_fence.p3_projection_heads AS PERMISSIVE FOR UPDATE TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app') WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app');
