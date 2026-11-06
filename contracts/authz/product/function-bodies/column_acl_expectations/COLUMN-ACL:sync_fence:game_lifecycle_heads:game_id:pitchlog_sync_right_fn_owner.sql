-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:game_lifecycle_heads:game_id:pitchlog_sync_right_fn_owner

GRANT SELECT (game_id),INSERT (game_id) ON TABLE sync_fence.game_lifecycle_heads TO pitchlog_sync_right_fn_owner;
