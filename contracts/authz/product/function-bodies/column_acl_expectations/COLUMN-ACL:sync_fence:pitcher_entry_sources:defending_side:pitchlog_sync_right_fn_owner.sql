-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:pitcher_entry_sources:defending_side:pitchlog_sync_right_fn_owner

GRANT SELECT (defending_side),INSERT (defending_side) ON sync_fence.pitcher_entry_sources TO pitchlog_sync_right_fn_owner;
