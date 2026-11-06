-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:request_fingerprint:pitchlog_sync_right_fn_owner

GRANT SELECT (request_fingerprint),INSERT (request_fingerprint) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
