-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:postmaster_started_at:pitchlog_sync_right_fn_owner

GRANT SELECT (postmaster_started_at),INSERT (postmaster_started_at) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
