-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:lease_id:pitchlog_sync_right_fn_owner

GRANT SELECT (lease_id),INSERT (lease_id) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
