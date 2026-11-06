-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:frame_digest:pitchlog_sync_right_fn_owner

GRANT SELECT (frame_digest),INSERT (frame_digest) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
