-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:migrated_final_lineups:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.migrated_final_lineups FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.migrated_final_lineups TO pitchlog_app;
