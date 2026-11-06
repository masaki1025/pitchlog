-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:system_identifier:pitchlog_sync_right_fn_owner

GRANT SELECT (system_identifier),INSERT (system_identifier) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
