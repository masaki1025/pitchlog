-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:pitcher_entry_sources:generation:pitchlog_sync_right_fn_owner

GRANT SELECT (generation),INSERT (generation) ON sync_fence.pitcher_entry_sources TO pitchlog_sync_right_fn_owner;
