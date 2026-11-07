-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_write_admissions:transaction_id:pitchlog_sync_right_fn_owner

GRANT SELECT (transaction_id),INSERT (transaction_id) ON sync_fence.p3_projection_write_admissions TO pitchlog_sync_right_fn_owner;
