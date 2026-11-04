-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:play_rows:ordinary_pitch_select_play_rows

CREATE POLICY ordinary_pitch_select_play_rows ON public.play_rows FOR SELECT TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app');
