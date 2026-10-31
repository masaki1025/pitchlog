-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:play_runners:responsible_pitcher_id:pitchlog_sync_right_fn_owner

GRANT SELECT (responsible_pitcher_id),INSERT (responsible_pitcher_id) ON TABLE public.play_runners TO pitchlog_sync_right_fn_owner;
