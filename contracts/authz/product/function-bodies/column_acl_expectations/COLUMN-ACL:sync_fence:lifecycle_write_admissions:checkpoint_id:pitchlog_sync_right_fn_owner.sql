-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:checkpoint_id:pitchlog_sync_right_fn_owner

GRANT SELECT (checkpoint_id),INSERT (checkpoint_id) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
