-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:system_settings:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.system_settings FROM PUBLIC, pitchlog_app;
GRANT SELECT ON TABLE public.system_settings TO pitchlog_app;
