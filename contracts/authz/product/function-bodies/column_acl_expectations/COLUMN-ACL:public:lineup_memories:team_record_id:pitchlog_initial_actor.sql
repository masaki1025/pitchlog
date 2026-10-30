-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:lineup_memories:team_record_id:pitchlog_initial_actor

GRANT SELECT (team_record_id), INSERT (team_record_id) ON TABLE public.lineup_memories TO pitchlog_initial_actor;
