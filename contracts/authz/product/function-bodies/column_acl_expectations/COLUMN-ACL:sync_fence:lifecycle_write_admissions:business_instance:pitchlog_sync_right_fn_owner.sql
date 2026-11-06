-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:business_instance:pitchlog_sync_right_fn_owner

GRANT SELECT (business_instance),INSERT (business_instance) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
