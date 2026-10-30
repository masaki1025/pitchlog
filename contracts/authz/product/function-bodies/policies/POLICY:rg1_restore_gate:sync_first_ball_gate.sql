-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:rg1_restore_gate:sync_first_ball_gate

CREATE POLICY sync_first_ball_gate ON public.rg1_restore_gate FOR SELECT TO pitchlog_sync_right_fn_owner USING (singleton_id=1);
