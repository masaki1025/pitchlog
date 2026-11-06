-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:expires_at:pitchlog_sync_right_fn_owner

GRANT SELECT (expires_at),INSERT (expires_at) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
