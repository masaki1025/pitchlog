-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:rg1_restore_gate:rg1_control_update_singleton

CREATE POLICY rg1_control_update_singleton ON public.rg1_restore_gate
    AS PERMISSIVE FOR UPDATE TO pitchlog_rg1_control_owner
    USING (singleton_id = 1)
    WITH CHECK (singleton_id = 1);
