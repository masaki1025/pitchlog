-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:system_vocabularies:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.system_vocabularies FROM PUBLIC, pitchlog_app;
GRANT SELECT ON TABLE public.system_vocabularies TO pitchlog_app;
