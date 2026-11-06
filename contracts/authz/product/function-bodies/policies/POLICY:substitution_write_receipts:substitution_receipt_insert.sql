-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:substitution_write_receipts:substitution_receipt_insert

CREATE POLICY substitution_receipt_insert ON sync_fence.substitution_write_receipts AS PERMISSIVE FOR INSERT TO pitchlog_sync_right_fn_owner WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app');
