-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_fact_versions:updated_at:pitchlog_sync_right_fn_owner

GRANT SELECT (updated_at),INSERT (updated_at),UPDATE (updated_at) ON sync_fence.stats_fact_versions TO pitchlog_sync_right_fn_owner;
