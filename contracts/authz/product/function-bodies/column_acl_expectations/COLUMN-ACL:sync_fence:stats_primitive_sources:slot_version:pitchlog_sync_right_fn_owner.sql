-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_primitive_sources:slot_version:pitchlog_sync_right_fn_owner

GRANT SELECT (slot_version),INSERT (slot_version) ON sync_fence.stats_primitive_sources TO pitchlog_sync_right_fn_owner;
