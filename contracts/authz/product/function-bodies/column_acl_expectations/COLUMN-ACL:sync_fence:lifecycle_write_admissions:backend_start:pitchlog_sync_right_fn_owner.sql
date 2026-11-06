-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:backend_start:pitchlog_sync_right_fn_owner

GRANT SELECT (backend_start),INSERT (backend_start) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
