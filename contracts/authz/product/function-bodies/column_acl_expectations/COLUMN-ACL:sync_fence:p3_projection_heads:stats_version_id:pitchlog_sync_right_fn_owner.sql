-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_heads:stats_version_id:pitchlog_sync_right_fn_owner

GRANT SELECT (stats_version_id),INSERT (stats_version_id),UPDATE (stats_version_id) ON sync_fence.p3_projection_heads TO pitchlog_sync_right_fn_owner;
