-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_fact_versions:source_set_sha256:pitchlog_sync_right_fn_owner

GRANT SELECT (source_set_sha256),INSERT (source_set_sha256),UPDATE (source_set_sha256) ON sync_fence.stats_fact_versions TO pitchlog_sync_right_fn_owner;
