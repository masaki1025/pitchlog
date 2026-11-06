-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:nonce_digest:pitchlog_sync_right_fn_owner

GRANT SELECT (nonce_digest),INSERT (nonce_digest) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
