-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:play_export_snapshots:play_export_snapshots_insert

CREATE POLICY play_export_snapshots_insert ON public.play_export_snapshots
  FOR INSERT TO pitchlog_sync_right_fn_owner
  WITH CHECK (
    tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid
    AND session_user = 'pitchlog_app'
    AND current_user = 'pitchlog_sync_right_fn_owner'
  );
