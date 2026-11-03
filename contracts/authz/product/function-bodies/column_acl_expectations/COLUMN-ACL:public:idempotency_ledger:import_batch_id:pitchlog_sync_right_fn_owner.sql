-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:idempotency_ledger:import_batch_id:pitchlog_sync_right_fn_owner

GRANT SELECT (import_batch_id) ON TABLE public.idempotency_ledger TO pitchlog_sync_right_fn_owner;
