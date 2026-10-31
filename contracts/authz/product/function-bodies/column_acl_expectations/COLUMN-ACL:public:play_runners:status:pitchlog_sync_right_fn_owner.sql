-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:play_runners:status:pitchlog_sync_right_fn_owner

GRANT SELECT (status),INSERT (status) ON TABLE public.play_runners TO pitchlog_sync_right_fn_owner;
