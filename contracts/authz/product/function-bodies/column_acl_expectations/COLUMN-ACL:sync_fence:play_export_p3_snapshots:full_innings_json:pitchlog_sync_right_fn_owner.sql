-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:play_export_p3_snapshots:full_innings_json:pitchlog_sync_right_fn_owner

GRANT SELECT (full_innings_json),INSERT (full_innings_json) ON sync_fence.play_export_p3_snapshots TO pitchlog_sync_right_fn_owner;
