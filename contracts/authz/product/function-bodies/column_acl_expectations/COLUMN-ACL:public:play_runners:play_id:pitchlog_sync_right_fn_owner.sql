-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:play_runners:play_id:pitchlog_sync_right_fn_owner

GRANT SELECT (play_id),INSERT (play_id) ON TABLE public.play_runners TO pitchlog_sync_right_fn_owner;
