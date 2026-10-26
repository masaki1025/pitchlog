-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:game_start_attempts:outcome:pitchlog_initial_fn_owner

GRANT SELECT (outcome), UPDATE (outcome) ON TABLE public.game_start_attempts TO pitchlog_initial_fn_owner;
