-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:recording_generations:recovery_generation:pitchlog_initial_fn_owner

GRANT SELECT (recovery_generation), INSERT (recovery_generation) ON TABLE public.recording_generations TO pitchlog_initial_fn_owner;
