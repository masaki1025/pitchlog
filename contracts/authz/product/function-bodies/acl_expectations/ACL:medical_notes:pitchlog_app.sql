-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:medical_notes:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.medical_notes FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.medical_notes TO pitchlog_app;
