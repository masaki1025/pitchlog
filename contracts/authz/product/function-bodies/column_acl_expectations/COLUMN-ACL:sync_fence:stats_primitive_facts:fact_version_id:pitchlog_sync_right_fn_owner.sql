-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_primitive_facts:fact_version_id:pitchlog_sync_right_fn_owner

GRANT SELECT (fact_version_id),INSERT (fact_version_id) ON sync_fence.stats_primitive_facts TO pitchlog_sync_right_fn_owner;
