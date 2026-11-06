-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:game_lifecycle_heads:is_finished:pitchlog_sync_right_fn_owner

GRANT SELECT (is_finished),INSERT (is_finished),UPDATE (is_finished) ON TABLE sync_fence.game_lifecycle_heads TO pitchlog_sync_right_fn_owner;
