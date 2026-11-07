-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_heads:capsule_id:pitchlog_sync_right_fn_owner

GRANT SELECT (capsule_id),INSERT (capsule_id),UPDATE (capsule_id) ON sync_fence.p3_projection_heads TO pitchlog_sync_right_fn_owner;
