-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:stats_fact_versions:stats_primitives_insert

CREATE POLICY stats_primitives_insert ON sync_fence.stats_fact_versions AS PERMISSIVE FOR INSERT TO pitchlog_sync_right_fn_owner WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app' AND completion_state='current_open');
