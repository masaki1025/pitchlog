-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_fact_versions:completion_state:pitchlog_sync_right_fn_owner

GRANT SELECT (completion_state),INSERT (completion_state) ON sync_fence.stats_fact_versions TO pitchlog_sync_right_fn_owner;
