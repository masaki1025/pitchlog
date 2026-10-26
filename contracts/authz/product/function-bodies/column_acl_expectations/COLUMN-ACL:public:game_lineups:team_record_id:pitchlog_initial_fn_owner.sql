-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:game_lineups:team_record_id:pitchlog_initial_fn_owner

GRANT SELECT (team_record_id), INSERT (team_record_id) ON TABLE public.game_lineups TO pitchlog_initial_fn_owner;
