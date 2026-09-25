-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:play_runners:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.play_runners FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.play_runners TO pitchlog_app;
