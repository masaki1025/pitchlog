-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:operation_events:first_ball_stamp_operation_events

CREATE POLICY first_ball_stamp_operation_events ON public.operation_events FOR SELECT TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid);
