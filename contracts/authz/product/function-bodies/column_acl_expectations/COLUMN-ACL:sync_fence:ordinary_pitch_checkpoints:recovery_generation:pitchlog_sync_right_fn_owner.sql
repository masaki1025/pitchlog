-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:recovery_generation:pitchlog_sync_right_fn_owner

GRANT SELECT (recovery_generation),INSERT (recovery_generation) ON TABLE sync_fence.ordinary_pitch_checkpoints TO pitchlog_sync_right_fn_owner;
