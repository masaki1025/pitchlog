-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:checkpoint_revision:pitchlog_sync_right_fn_owner

GRANT SELECT (checkpoint_revision),INSERT (checkpoint_revision) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
