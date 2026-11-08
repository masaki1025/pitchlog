-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:play_export_p3_snapshots:effective_play_row_id:pitchlog_sync_right_fn_owner

GRANT SELECT (effective_play_row_id),INSERT (effective_play_row_id) ON sync_fence.play_export_p3_snapshots TO pitchlog_sync_right_fn_owner;
