-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:revision:pitchlog_sync_right_fn_owner

GRANT SELECT (revision),INSERT (revision),UPDATE (revision) ON TABLE sync_fence.ordinary_pitch_checkpoints TO pitchlog_sync_right_fn_owner;
