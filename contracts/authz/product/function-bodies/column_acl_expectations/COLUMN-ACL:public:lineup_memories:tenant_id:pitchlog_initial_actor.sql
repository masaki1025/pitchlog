-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:lineup_memories:tenant_id:pitchlog_initial_actor

GRANT SELECT (tenant_id), INSERT (tenant_id) ON TABLE public.lineup_memories TO pitchlog_initial_actor;
