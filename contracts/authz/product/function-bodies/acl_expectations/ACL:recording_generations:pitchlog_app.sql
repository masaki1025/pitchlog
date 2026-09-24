-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:recording_generations:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.recording_generations FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.recording_generations TO pitchlog_app;
