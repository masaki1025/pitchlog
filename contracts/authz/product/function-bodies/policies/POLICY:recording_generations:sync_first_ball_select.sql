-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:recording_generations:sync_first_ball_select

CREATE POLICY sync_first_ball_select ON public.recording_generations FOR SELECT TO pitchlog_sync_right_fn_owner USING (tenant_id=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid);
