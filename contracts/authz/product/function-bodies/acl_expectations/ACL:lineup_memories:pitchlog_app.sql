-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:lineup_memories:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.lineup_memories FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.lineup_memories TO pitchlog_app;
