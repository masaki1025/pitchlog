-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:game_lifecycle_heads:active_stats_version_id:pitchlog_sync_right_fn_owner

GRANT SELECT (active_stats_version_id),INSERT (active_stats_version_id),UPDATE (active_stats_version_id) ON TABLE sync_fence.game_lifecycle_heads TO pitchlog_sync_right_fn_owner;
