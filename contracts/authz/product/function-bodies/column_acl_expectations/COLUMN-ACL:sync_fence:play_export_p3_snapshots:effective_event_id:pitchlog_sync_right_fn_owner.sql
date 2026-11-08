-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:play_export_p3_snapshots:effective_event_id:pitchlog_sync_right_fn_owner

GRANT SELECT (effective_event_id),INSERT (effective_event_id) ON sync_fence.play_export_p3_snapshots TO pitchlog_sync_right_fn_owner;
