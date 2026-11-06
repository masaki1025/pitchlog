-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:preparation:pitchlog_sync_right_fn_owner

GRANT SELECT (preparation),INSERT (preparation) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
