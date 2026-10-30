-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:lineup_memories:lineup:pitchlog_initial_actor

GRANT SELECT (lineup), INSERT (lineup), UPDATE (lineup) ON TABLE public.lineup_memories TO pitchlog_initial_actor;
