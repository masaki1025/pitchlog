-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:play_export_p3_snapshots:play_row_version:pitchlog_sync_right_fn_owner

GRANT SELECT (play_row_version),INSERT (play_row_version) ON sync_fence.play_export_p3_snapshots TO pitchlog_sync_right_fn_owner;
