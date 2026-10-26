-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:recording_generations:generation:pitchlog_initial_fn_owner

GRANT SELECT (generation), INSERT (generation), UPDATE (generation) ON TABLE public.recording_generations TO pitchlog_initial_fn_owner;
