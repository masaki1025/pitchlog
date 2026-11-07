-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_fact_versions:model_sha256:pitchlog_sync_right_fn_owner

GRANT SELECT (model_sha256),INSERT (model_sha256) ON sync_fence.stats_fact_versions TO pitchlog_sync_right_fn_owner;
