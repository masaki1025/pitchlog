-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:medical_note_versions:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.medical_note_versions FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.medical_note_versions TO pitchlog_app;
