-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:game_lineups:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.game_lineups FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.game_lineups TO pitchlog_app;
