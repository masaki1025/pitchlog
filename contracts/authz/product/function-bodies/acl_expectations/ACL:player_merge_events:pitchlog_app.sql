-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:player_merge_events:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.player_merge_events FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.player_merge_events TO pitchlog_app;
