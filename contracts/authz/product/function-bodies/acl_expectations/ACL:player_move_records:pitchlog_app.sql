-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:player_move_records:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.player_move_records FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.player_move_records TO pitchlog_app;
