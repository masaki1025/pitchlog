-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:recording_generations:tenant_id:pitchlog_app

REVOKE SELECT, INSERT, UPDATE ON TABLE public.recording_generations FROM pitchlog_app;
GRANT SELECT (tenant_id), UPDATE (tenant_id) ON TABLE public.recording_generations TO pitchlog_app;
