-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:artifact_sha256:pitchlog_sync_right_fn_owner

GRANT SELECT (artifact_sha256),INSERT (artifact_sha256) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
