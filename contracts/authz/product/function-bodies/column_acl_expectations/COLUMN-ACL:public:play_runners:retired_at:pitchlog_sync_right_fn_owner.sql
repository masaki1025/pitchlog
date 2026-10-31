-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:play_runners:retired_at:pitchlog_sync_right_fn_owner

GRANT SELECT (retired_at),INSERT (retired_at) ON TABLE public.play_runners TO pitchlog_sync_right_fn_owner;
