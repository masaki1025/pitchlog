-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_primitive_sources:checkpoint_revision:pitchlog_sync_right_fn_owner

GRANT SELECT (checkpoint_revision),INSERT (checkpoint_revision) ON sync_fence.stats_primitive_sources TO pitchlog_sync_right_fn_owner;
