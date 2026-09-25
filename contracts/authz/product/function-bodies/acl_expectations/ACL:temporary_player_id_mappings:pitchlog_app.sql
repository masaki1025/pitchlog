-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:temporary_player_id_mappings:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.temporary_player_id_mappings FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.temporary_player_id_mappings TO pitchlog_app;
