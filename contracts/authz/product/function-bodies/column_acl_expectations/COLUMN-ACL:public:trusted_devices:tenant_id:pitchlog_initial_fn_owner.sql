-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:trusted_devices:tenant_id:pitchlog_initial_fn_owner

GRANT SELECT (tenant_id), INSERT (tenant_id) ON TABLE public.trusted_devices TO pitchlog_initial_fn_owner;
