-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:tenant_vocabularies:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.tenant_vocabularies FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.tenant_vocabularies TO pitchlog_app;
