-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_fact_versions:source_count:pitchlog_sync_right_fn_owner

GRANT SELECT (source_count),INSERT (source_count),UPDATE (source_count) ON sync_fence.stats_fact_versions TO pitchlog_sync_right_fn_owner;
