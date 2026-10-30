-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:roster:pitchlog_sync_right_fn_owner

GRANT SELECT (roster),INSERT (roster),UPDATE (roster) ON TABLE sync_fence.ordinary_pitch_checkpoints TO pitchlog_sync_right_fn_owner;
