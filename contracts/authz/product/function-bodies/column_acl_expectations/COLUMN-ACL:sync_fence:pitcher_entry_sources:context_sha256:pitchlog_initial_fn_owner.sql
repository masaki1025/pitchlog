-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:pitcher_entry_sources:context_sha256:pitchlog_initial_fn_owner

GRANT SELECT (context_sha256),INSERT (context_sha256) ON sync_fence.pitcher_entry_sources TO pitchlog_initial_fn_owner;
