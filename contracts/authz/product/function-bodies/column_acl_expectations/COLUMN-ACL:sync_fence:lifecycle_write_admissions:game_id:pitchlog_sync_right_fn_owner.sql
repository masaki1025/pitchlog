-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:game_id:pitchlog_sync_right_fn_owner

GRANT SELECT (game_id),INSERT (game_id) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
