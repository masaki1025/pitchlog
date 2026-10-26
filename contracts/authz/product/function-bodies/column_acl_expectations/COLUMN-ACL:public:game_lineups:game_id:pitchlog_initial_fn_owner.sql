-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:game_lineups:game_id:pitchlog_initial_fn_owner

GRANT SELECT (game_id), INSERT (game_id) ON TABLE public.game_lineups TO pitchlog_initial_fn_owner;
