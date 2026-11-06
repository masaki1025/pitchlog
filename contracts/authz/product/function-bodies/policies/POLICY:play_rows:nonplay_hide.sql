-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:play_rows:nonplay_hide

CREATE POLICY nonplay_hide ON public.play_rows AS PERMISSIVE FOR UPDATE TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app') WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app');
