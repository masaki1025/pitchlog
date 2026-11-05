-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_fact_versions:completion_receipt_id:pitchlog_sync_right_fn_owner

GRANT SELECT (completion_receipt_id),INSERT (completion_receipt_id) ON sync_fence.stats_fact_versions TO pitchlog_sync_right_fn_owner;
