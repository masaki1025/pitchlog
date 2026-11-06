-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:recovery_generation:pitchlog_sync_right_fn_owner

GRANT SELECT (recovery_generation),INSERT (recovery_generation) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
