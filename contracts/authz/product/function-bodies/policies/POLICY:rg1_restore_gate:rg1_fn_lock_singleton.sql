-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:rg1_restore_gate:rg1_fn_lock_singleton

CREATE POLICY rg1_fn_lock_singleton ON public.rg1_restore_gate
    AS PERMISSIVE FOR UPDATE TO pitchlog_rg1_fn_owner
    USING (singleton_id = 1)
    WITH CHECK (singleton_id = 1);
