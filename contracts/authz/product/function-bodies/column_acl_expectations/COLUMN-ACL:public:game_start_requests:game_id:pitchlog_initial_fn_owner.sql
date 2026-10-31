-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:game_start_requests:game_id:pitchlog_initial_fn_owner

GRANT SELECT (game_id), INSERT (game_id) ON TABLE public.game_start_requests TO pitchlog_initial_fn_owner;
