-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:play_export_snapshots:play_export_snapshots_select

CREATE POLICY play_export_snapshots_select ON public.play_export_snapshots
  FOR SELECT TO pitchlog_app
  USING (
    tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid
    AND session_user = 'pitchlog_app'
  );
