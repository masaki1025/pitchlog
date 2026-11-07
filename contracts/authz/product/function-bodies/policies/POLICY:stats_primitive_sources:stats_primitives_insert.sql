-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:stats_primitive_sources:stats_primitives_insert

CREATE POLICY stats_primitives_insert ON sync_fence.stats_primitive_sources AS PERMISSIVE FOR INSERT TO pitchlog_sync_right_fn_owner WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app' AND EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions v WHERE v.tenant_id=stats_primitive_sources.tenant_id AND v.game_id=stats_primitive_sources.game_id AND v.id=stats_primitive_sources.fact_version_id AND v.is_current AND v.invalidated_at IS NULL AND v.completion_state='current_open'));
