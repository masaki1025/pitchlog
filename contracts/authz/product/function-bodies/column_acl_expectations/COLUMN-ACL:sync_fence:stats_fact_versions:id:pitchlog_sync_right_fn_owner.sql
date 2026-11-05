-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_fact_versions:id:pitchlog_sync_right_fn_owner

GRANT SELECT (id),INSERT (id) ON sync_fence.stats_fact_versions TO pitchlog_sync_right_fn_owner;
