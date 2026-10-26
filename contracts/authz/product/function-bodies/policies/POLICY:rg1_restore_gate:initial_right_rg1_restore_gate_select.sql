-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:rg1_restore_gate:initial_right_rg1_restore_gate_select

CREATE POLICY initial_right_rg1_restore_gate_select ON public.rg1_restore_gate
AS PERMISSIVE FOR SELECT TO pitchlog_initial_fn_owner
USING (singleton_id = 1);
