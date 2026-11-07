-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:pitcher_entry_sources:inning:pitchlog_sync_right_fn_owner

GRANT SELECT (inning),INSERT (inning) ON sync_fence.pitcher_entry_sources TO pitchlog_sync_right_fn_owner;
