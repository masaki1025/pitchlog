-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_capsules:created_at:pitchlog_sync_right_fn_owner

GRANT SELECT (created_at),INSERT (created_at) ON sync_fence.p3_projection_capsules TO pitchlog_sync_right_fn_owner;
