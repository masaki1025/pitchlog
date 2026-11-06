-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:checkpoint_digest:pitchlog_sync_right_fn_owner

GRANT SELECT (checkpoint_digest),INSERT (checkpoint_digest) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
