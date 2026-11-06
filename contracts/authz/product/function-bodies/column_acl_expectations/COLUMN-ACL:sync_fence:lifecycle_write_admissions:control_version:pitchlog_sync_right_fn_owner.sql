-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:control_version:pitchlog_sync_right_fn_owner

GRANT SELECT (control_version),INSERT (control_version) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
