-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:pitcher_entry_sources:source_event_id:pitchlog_initial_fn_owner

GRANT SELECT (source_event_id),INSERT (source_event_id) ON sync_fence.pitcher_entry_sources TO pitchlog_initial_fn_owner;
