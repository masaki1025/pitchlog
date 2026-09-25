-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:play_rows:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.play_rows FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.play_rows TO pitchlog_app;
