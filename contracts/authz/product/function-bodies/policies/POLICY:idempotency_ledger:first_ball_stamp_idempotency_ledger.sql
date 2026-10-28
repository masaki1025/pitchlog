-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:idempotency_ledger:first_ball_stamp_idempotency_ledger

CREATE POLICY first_ball_stamp_idempotency_ledger ON public.idempotency_ledger FOR SELECT TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid);
