-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:pitcher_entry_sources:start_attempt_id:pitchlog_sync_right_fn_owner

GRANT SELECT (start_attempt_id),INSERT (start_attempt_id) ON sync_fence.pitcher_entry_sources TO pitchlog_sync_right_fn_owner;
