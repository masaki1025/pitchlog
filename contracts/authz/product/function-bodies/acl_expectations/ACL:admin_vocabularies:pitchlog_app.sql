-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:admin_vocabularies:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.admin_vocabularies FROM PUBLIC, pitchlog_app;
GRANT SELECT ON TABLE public.admin_vocabularies TO pitchlog_app;
