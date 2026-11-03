-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:idempotency_ledger:source_fingerprint:pitchlog_sync_right_fn_owner

GRANT SELECT (source_fingerprint) ON TABLE public.idempotency_ledger TO pitchlog_sync_right_fn_owner;
