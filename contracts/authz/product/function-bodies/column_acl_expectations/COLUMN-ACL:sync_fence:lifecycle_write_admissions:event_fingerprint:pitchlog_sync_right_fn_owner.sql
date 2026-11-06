-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:event_fingerprint:pitchlog_sync_right_fn_owner

GRANT SELECT (event_fingerprint),INSERT (event_fingerprint) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
