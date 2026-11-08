-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:play_export_p3_snapshots:plays_csv_json:pitchlog_sync_right_fn_owner

GRANT SELECT (plays_csv_json),INSERT (plays_csv_json) ON sync_fence.play_export_p3_snapshots TO pitchlog_sync_right_fn_owner;
