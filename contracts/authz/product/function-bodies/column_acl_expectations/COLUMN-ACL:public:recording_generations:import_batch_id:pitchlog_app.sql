-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:recording_generations:import_batch_id:pitchlog_app

GRANT SELECT (import_batch_id), UPDATE (import_batch_id) ON TABLE public.recording_generations TO pitchlog_app;
