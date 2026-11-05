-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_fact_versions:last_generation:pitchlog_sync_right_fn_owner

GRANT SELECT (last_generation),INSERT (last_generation),UPDATE (last_generation) ON sync_fence.stats_fact_versions TO pitchlog_sync_right_fn_owner;
