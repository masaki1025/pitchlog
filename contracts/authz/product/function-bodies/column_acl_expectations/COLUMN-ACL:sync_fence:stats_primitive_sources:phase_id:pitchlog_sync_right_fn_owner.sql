-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_primitive_sources:phase_id:pitchlog_sync_right_fn_owner

GRANT SELECT (phase_id),INSERT (phase_id) ON sync_fence.stats_primitive_sources TO pitchlog_sync_right_fn_owner;
