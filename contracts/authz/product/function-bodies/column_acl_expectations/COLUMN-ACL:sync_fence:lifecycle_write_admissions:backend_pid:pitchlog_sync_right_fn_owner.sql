-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:backend_pid:pitchlog_sync_right_fn_owner

GRANT SELECT (backend_pid),INSERT (backend_pid) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
