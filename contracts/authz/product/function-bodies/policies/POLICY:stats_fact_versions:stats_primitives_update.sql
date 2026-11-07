-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:stats_fact_versions:stats_primitives_update

CREATE POLICY stats_primitives_update ON sync_fence.stats_fact_versions AS PERMISSIVE FOR UPDATE TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app' AND completion_state='current_open') WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app' AND completion_state='current_open');
