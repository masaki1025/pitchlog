-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:restore_epoch:pitchlog_sync_right_fn_owner

GRANT SELECT (restore_epoch),INSERT (restore_epoch) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
