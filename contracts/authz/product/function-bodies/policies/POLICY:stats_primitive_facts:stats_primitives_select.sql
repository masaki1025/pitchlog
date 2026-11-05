-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:stats_primitive_facts:stats_primitives_select

CREATE POLICY stats_primitives_select ON sync_fence.stats_primitive_facts AS PERMISSIVE FOR SELECT TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app');
