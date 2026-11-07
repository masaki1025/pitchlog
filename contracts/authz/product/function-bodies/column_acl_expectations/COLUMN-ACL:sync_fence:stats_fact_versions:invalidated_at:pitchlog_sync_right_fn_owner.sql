-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_fact_versions:invalidated_at:pitchlog_sync_right_fn_owner

GRANT SELECT (invalidated_at),INSERT (invalidated_at),UPDATE (invalidated_at) ON sync_fence.stats_fact_versions TO pitchlog_sync_right_fn_owner;
