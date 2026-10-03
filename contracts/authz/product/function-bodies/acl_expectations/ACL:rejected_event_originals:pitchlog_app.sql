-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:rejected_event_originals:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.rejected_event_originals FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.rejected_event_originals TO pitchlog_app;
