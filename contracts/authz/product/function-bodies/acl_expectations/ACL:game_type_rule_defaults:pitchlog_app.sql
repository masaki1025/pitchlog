-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:game_type_rule_defaults:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.game_type_rule_defaults FROM PUBLIC, pitchlog_app;
GRANT SELECT ON TABLE public.game_type_rule_defaults TO pitchlog_app;
