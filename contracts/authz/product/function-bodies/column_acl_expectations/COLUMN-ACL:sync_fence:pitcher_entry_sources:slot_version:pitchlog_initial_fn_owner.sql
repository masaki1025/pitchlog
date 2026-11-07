-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:pitcher_entry_sources:slot_version:pitchlog_initial_fn_owner

GRANT SELECT (slot_version),INSERT (slot_version) ON sync_fence.pitcher_entry_sources TO pitchlog_initial_fn_owner;
