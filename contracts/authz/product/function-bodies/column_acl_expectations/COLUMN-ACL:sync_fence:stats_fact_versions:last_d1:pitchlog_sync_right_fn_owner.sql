-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_fact_versions:last_d1:pitchlog_sync_right_fn_owner

GRANT SELECT (last_d1),INSERT (last_d1),UPDATE (last_d1) ON sync_fence.stats_fact_versions TO pitchlog_sync_right_fn_owner;
