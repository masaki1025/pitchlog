-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_primitive_facts:amount:pitchlog_sync_right_fn_owner

GRANT SELECT (amount),INSERT (amount) ON sync_fence.stats_primitive_facts TO pitchlog_sync_right_fn_owner;
