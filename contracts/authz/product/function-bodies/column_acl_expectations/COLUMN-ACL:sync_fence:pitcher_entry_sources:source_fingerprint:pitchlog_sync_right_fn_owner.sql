-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:pitcher_entry_sources:source_fingerprint:pitchlog_sync_right_fn_owner

GRANT SELECT (source_fingerprint),INSERT (source_fingerprint) ON sync_fence.pitcher_entry_sources TO pitchlog_sync_right_fn_owner;
