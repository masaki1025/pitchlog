-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_fact_versions:revision:pitchlog_sync_right_fn_owner

GRANT SELECT (revision),INSERT (revision),UPDATE (revision) ON sync_fence.stats_fact_versions TO pitchlog_sync_right_fn_owner;
