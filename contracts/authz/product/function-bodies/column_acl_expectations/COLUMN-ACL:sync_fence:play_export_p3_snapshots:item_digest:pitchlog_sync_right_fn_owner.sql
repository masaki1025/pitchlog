-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:play_export_p3_snapshots:item_digest:pitchlog_sync_right_fn_owner

GRANT SELECT (item_digest),INSERT (item_digest) ON sync_fence.play_export_p3_snapshots TO pitchlog_sync_right_fn_owner;
