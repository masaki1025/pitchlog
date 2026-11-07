-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_page_progress:old_stats_version_id:pitchlog_sync_right_fn_owner

GRANT SELECT (old_stats_version_id),INSERT (old_stats_version_id) ON sync_fence.p3_projection_page_progress TO pitchlog_sync_right_fn_owner;
