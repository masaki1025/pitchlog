-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:trusted_devices:sync_first_ball_device_lock

CREATE POLICY sync_first_ball_device_lock ON public.trusted_devices FOR UPDATE TO pitchlog_sync_right_fn_owner USING (tenant_id=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid) WITH CHECK (tenant_id=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid);
