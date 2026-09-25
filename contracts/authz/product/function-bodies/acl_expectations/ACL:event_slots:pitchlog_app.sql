-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:event_slots:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.event_slots FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.event_slots TO pitchlog_app;
