-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:tenants:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.tenants FROM PUBLIC, pitchlog_app;
GRANT SELECT ON TABLE public.tenants TO pitchlog_app;
