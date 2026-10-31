-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:game_start_attempts:tenant_id:pitchlog_initial_fn_owner

GRANT SELECT (tenant_id), INSERT (tenant_id) ON TABLE public.game_start_attempts TO pitchlog_initial_fn_owner;
