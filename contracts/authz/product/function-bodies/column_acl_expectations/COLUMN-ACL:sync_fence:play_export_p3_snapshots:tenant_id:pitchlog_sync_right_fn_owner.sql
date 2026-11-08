-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:play_export_p3_snapshots:tenant_id:pitchlog_sync_right_fn_owner

GRANT SELECT (tenant_id),INSERT (tenant_id) ON sync_fence.play_export_p3_snapshots TO pitchlog_sync_right_fn_owner;
