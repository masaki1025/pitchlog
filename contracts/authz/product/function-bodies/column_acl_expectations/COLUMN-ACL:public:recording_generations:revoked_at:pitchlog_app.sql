-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:recording_generations:revoked_at:pitchlog_app

GRANT SELECT (revoked_at), UPDATE (revoked_at) ON TABLE public.recording_generations TO pitchlog_app;
