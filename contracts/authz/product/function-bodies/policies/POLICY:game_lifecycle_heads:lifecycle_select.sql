-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:game_lifecycle_heads:lifecycle_select

CREATE POLICY lifecycle_select ON sync_fence.game_lifecycle_heads AS PERMISSIVE FOR SELECT TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app');
