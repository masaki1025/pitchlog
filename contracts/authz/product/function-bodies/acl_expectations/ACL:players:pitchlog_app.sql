-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:players:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.players FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.players TO pitchlog_app;
