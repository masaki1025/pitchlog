-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:pitcher_entry_sources:player_id:pitchlog_sync_right_fn_owner

GRANT SELECT (player_id),INSERT (player_id) ON sync_fence.pitcher_entry_sources TO pitchlog_sync_right_fn_owner;
