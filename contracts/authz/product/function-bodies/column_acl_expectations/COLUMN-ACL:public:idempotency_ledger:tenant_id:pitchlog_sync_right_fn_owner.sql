-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:idempotency_ledger:tenant_id:pitchlog_sync_right_fn_owner

GRANT SELECT (tenant_id) ON TABLE public.idempotency_ledger TO pitchlog_sync_right_fn_owner;
