-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:play_export_snapshots:play_export_snapshots_p3_select

CREATE POLICY play_export_snapshots_p3_select ON public.play_export_snapshots AS PERMISSIVE FOR SELECT TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid);
