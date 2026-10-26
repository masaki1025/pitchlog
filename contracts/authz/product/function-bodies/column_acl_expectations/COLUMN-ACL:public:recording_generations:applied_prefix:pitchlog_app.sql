-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:recording_generations:applied_prefix:pitchlog_app

GRANT SELECT (applied_prefix), UPDATE (applied_prefix) ON TABLE public.recording_generations TO pitchlog_app;
