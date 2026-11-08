-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:play_export_p3_snapshots:play_export_p3_snapshots_insert

CREATE POLICY play_export_p3_snapshots_insert ON sync_fence.play_export_p3_snapshots AS PERMISSIVE FOR INSERT TO pitchlog_sync_right_fn_owner WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid);
