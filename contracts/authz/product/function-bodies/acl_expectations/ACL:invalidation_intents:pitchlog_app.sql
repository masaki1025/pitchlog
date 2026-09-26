-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:invalidation_intents:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.invalidation_intents FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.invalidation_intents TO pitchlog_app;
