-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:rg1_restore_gate:rg1_fn_select_singleton

CREATE POLICY rg1_fn_select_singleton ON public.rg1_restore_gate
    AS PERMISSIVE FOR SELECT TO pitchlog_rg1_fn_owner
    USING (singleton_id = 1);
