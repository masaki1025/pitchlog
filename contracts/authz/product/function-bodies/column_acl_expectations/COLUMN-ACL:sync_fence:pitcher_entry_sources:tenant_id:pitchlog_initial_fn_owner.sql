-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:pitcher_entry_sources:tenant_id:pitchlog_initial_fn_owner

GRANT SELECT (tenant_id),INSERT (tenant_id) ON sync_fence.pitcher_entry_sources TO pitchlog_initial_fn_owner;
