-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:idempotency_ledger:binding_d5_read

CREATE POLICY binding_d5_read ON public.idempotency_ledger FOR SELECT TO pitchlog_sync_binding_fn_owner USING (true);
