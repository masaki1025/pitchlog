-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_fact_versions:computed_metric_keys:pitchlog_sync_right_fn_owner

GRANT SELECT (computed_metric_keys),INSERT (computed_metric_keys),UPDATE (computed_metric_keys) ON sync_fence.stats_fact_versions TO pitchlog_sync_right_fn_owner;
