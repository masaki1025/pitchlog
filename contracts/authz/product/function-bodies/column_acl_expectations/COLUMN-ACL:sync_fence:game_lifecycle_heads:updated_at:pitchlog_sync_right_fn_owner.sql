-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:game_lifecycle_heads:updated_at:pitchlog_sync_right_fn_owner

GRANT SELECT (updated_at),INSERT (updated_at),UPDATE (updated_at) ON TABLE sync_fence.game_lifecycle_heads TO pitchlog_sync_right_fn_owner;
