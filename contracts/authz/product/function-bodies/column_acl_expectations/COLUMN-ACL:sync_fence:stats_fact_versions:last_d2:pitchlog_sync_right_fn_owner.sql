-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_fact_versions:last_d2:pitchlog_sync_right_fn_owner

GRANT SELECT (last_d2),INSERT (last_d2),UPDATE (last_d2) ON sync_fence.stats_fact_versions TO pitchlog_sync_right_fn_owner;
