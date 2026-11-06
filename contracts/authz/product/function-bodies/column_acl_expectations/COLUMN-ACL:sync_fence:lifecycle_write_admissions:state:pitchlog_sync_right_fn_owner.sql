-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:state:pitchlog_sync_right_fn_owner

GRANT SELECT (state),INSERT (state),UPDATE (state) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
