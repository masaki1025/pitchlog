-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:pitcher_entry_sources:origin_kind:pitchlog_sync_right_fn_owner

GRANT SELECT (origin_kind),INSERT (origin_kind) ON sync_fence.pitcher_entry_sources TO pitchlog_sync_right_fn_owner;
