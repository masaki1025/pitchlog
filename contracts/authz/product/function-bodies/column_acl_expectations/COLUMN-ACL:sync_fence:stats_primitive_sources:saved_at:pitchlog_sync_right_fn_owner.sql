-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_primitive_sources:saved_at:pitchlog_sync_right_fn_owner

GRANT SELECT (saved_at),INSERT (saved_at) ON sync_fence.stats_primitive_sources TO pitchlog_sync_right_fn_owner;
