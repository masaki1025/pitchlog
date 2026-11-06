-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:consumed_at:pitchlog_sync_right_fn_owner

GRANT SELECT (consumed_at),INSERT (consumed_at),UPDATE (consumed_at) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
