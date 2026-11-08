-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:play_export_snapshots:game_id:pitchlog_sync_right_fn_owner

GRANT SELECT (game_id),INSERT (game_id) ON public.play_export_snapshots TO pitchlog_sync_right_fn_owner;
