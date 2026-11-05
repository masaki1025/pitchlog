-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_primitive_sources:artifact_sha256:pitchlog_sync_right_fn_owner

GRANT SELECT (artifact_sha256),INSERT (artifact_sha256) ON sync_fence.stats_primitive_sources TO pitchlog_sync_right_fn_owner;
