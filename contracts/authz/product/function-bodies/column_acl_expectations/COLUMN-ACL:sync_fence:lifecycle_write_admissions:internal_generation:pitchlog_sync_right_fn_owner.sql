-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:internal_generation:pitchlog_sync_right_fn_owner

GRANT SELECT (internal_generation),INSERT (internal_generation) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
