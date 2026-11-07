-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:pitcher_entry_sources:proof_sha256:pitchlog_sync_right_fn_owner

GRANT SELECT (proof_sha256),INSERT (proof_sha256) ON sync_fence.pitcher_entry_sources TO pitchlog_sync_right_fn_owner;
