-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:recording_generations:tenant_id:pitchlog_initial_fn_owner

GRANT SELECT (tenant_id), INSERT (tenant_id) ON TABLE public.recording_generations TO pitchlog_initial_fn_owner;
