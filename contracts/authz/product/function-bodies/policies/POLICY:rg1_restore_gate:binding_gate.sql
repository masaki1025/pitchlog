-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:rg1_restore_gate:binding_gate

CREATE POLICY binding_gate ON public.rg1_restore_gate FOR SELECT TO pitchlog_sync_binding_fn_owner USING (singleton_id=1);
