-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:games:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.games FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.games TO pitchlog_app;
