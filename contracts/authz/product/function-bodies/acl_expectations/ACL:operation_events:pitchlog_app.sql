-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:operation_events:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.operation_events FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.operation_events TO pitchlog_app;
