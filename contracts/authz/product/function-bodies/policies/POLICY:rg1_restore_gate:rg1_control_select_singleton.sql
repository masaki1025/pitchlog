-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:rg1_restore_gate:rg1_control_select_singleton

CREATE POLICY rg1_control_select_singleton ON public.rg1_restore_gate
    AS PERMISSIVE FOR SELECT TO pitchlog_rg1_control_owner
    USING (singleton_id = 1);
