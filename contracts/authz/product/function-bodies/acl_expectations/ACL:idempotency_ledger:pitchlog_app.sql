-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:idempotency_ledger:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.idempotency_ledger FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.idempotency_ledger TO pitchlog_app;
