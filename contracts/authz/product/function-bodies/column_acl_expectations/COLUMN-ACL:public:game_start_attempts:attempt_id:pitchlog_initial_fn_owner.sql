-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:game_start_attempts:attempt_id:pitchlog_initial_fn_owner

GRANT SELECT (attempt_id), INSERT (attempt_id) ON TABLE public.game_start_attempts TO pitchlog_initial_fn_owner;
