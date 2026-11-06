-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:preparation_json:pitchlog_sync_right_fn_owner

GRANT SELECT (preparation_json),INSERT (preparation_json) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
