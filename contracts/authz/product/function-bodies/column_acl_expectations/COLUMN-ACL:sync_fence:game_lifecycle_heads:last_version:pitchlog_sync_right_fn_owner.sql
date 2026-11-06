-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:game_lifecycle_heads:last_version:pitchlog_sync_right_fn_owner

GRANT SELECT (last_version),INSERT (last_version),UPDATE (last_version) ON TABLE sync_fence.game_lifecycle_heads TO pitchlog_sync_right_fn_owner;
