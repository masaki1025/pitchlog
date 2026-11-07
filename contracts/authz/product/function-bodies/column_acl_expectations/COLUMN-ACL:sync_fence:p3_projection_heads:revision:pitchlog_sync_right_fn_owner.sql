-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_heads:revision:pitchlog_sync_right_fn_owner

GRANT SELECT (revision),INSERT (revision),UPDATE (revision) ON sync_fence.p3_projection_heads TO pitchlog_sync_right_fn_owner;
