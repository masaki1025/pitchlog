-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:action:pitchlog_sync_right_fn_owner

GRANT SELECT (action),INSERT (action) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
