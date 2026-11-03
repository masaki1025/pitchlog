-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:trusted_devices:sync_first_ball_select

CREATE POLICY sync_first_ball_select ON public.trusted_devices FOR SELECT TO pitchlog_sync_right_fn_owner USING (tenant_id=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid);
