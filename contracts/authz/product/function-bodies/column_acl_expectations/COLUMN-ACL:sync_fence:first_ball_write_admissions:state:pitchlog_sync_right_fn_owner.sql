-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:first_ball_write_admissions:state:pitchlog_sync_right_fn_owner

GRANT INSERT (state),UPDATE (state) ON TABLE sync_fence.first_ball_write_admissions TO pitchlog_sync_right_fn_owner;
