-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:saved_at:pitchlog_sync_right_fn_owner

GRANT SELECT (saved_at),INSERT (saved_at),UPDATE (saved_at) ON TABLE sync_fence.ordinary_pitch_checkpoints TO pitchlog_sync_right_fn_owner;
