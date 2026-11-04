-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:play_runners:runner_id:pitchlog_sync_right_fn_owner

GRANT SELECT (runner_id),INSERT (runner_id) ON TABLE public.play_runners TO pitchlog_sync_right_fn_owner;
