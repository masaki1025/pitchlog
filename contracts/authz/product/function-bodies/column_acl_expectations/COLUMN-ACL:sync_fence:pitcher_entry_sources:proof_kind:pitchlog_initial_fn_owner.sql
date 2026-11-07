-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:pitcher_entry_sources:proof_kind:pitchlog_initial_fn_owner

GRANT SELECT (proof_kind),INSERT (proof_kind) ON sync_fence.pitcher_entry_sources TO pitchlog_initial_fn_owner;
