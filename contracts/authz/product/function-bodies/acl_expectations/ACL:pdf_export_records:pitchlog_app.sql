-- ELEMENT-TYPE: acl_expectation
-- ELEMENT-ID: ACL:pdf_export_records:pitchlog_app

REVOKE ALL PRIVILEGES ON TABLE public.pdf_export_records FROM PUBLIC, pitchlog_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.pdf_export_records TO pitchlog_app;
