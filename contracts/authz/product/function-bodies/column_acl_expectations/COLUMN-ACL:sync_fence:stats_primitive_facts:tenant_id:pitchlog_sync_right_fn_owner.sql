-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_primitive_facts:tenant_id:pitchlog_sync_right_fn_owner

GRANT SELECT (tenant_id),INSERT (tenant_id) ON sync_fence.stats_primitive_facts TO pitchlog_sync_right_fn_owner;
