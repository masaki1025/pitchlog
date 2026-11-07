-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_write_admissions:state:pitchlog_sync_right_fn_owner

GRANT SELECT (state),INSERT (state),UPDATE (state) ON sync_fence.p3_projection_write_admissions TO pitchlog_sync_right_fn_owner;
