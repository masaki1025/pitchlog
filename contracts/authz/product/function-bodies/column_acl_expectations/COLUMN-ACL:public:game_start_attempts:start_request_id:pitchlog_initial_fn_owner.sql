-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:game_start_attempts:start_request_id:pitchlog_initial_fn_owner

GRANT SELECT (start_request_id), INSERT (start_request_id) ON TABLE public.game_start_attempts TO pitchlog_initial_fn_owner;
