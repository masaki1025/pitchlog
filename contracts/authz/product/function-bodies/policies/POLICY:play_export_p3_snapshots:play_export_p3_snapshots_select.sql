-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:play_export_p3_snapshots:play_export_p3_snapshots_select

CREATE POLICY play_export_p3_snapshots_select ON sync_fence.play_export_p3_snapshots AS PERMISSIVE FOR SELECT TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid);
