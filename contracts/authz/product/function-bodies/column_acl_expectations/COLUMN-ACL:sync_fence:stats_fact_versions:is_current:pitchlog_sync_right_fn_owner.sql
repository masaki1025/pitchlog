-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_fact_versions:is_current:pitchlog_sync_right_fn_owner

GRANT SELECT (is_current),INSERT (is_current),UPDATE (is_current) ON sync_fence.stats_fact_versions TO pitchlog_sync_right_fn_owner;
