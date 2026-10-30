-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:state:pitchlog_sync_right_fn_owner

GRANT SELECT (state),INSERT (state),UPDATE (state) ON TABLE sync_fence.ordinary_pitch_checkpoints TO pitchlog_sync_right_fn_owner;
