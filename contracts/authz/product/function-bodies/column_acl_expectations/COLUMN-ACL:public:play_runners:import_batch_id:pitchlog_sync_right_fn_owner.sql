-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:play_runners:import_batch_id:pitchlog_sync_right_fn_owner

GRANT SELECT (import_batch_id),INSERT (import_batch_id) ON TABLE public.play_runners TO pitchlog_sync_right_fn_owner;
