-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:participation_intervals:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.participation_intervals FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.participation_intervals TO pitchlog_app;
