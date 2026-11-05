-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_primitive_sources:checkpoint_id:pitchlog_sync_right_fn_owner

GRANT SELECT (checkpoint_id),INSERT (checkpoint_id) ON sync_fence.stats_primitive_sources TO pitchlog_sync_right_fn_owner;
