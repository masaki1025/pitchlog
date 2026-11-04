-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:ordinary_pitch_history:game_id:pitchlog_sync_right_fn_owner

GRANT SELECT (game_id),INSERT (game_id) ON TABLE sync_fence.ordinary_pitch_history TO pitchlog_sync_right_fn_owner;
