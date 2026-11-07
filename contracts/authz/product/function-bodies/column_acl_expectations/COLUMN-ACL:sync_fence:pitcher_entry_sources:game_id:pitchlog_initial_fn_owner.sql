-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:pitcher_entry_sources:game_id:pitchlog_initial_fn_owner

GRANT SELECT (game_id),INSERT (game_id) ON sync_fence.pitcher_entry_sources TO pitchlog_initial_fn_owner;
