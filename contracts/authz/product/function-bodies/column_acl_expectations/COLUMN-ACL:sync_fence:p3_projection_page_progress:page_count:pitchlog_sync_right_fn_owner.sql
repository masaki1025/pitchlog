-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_page_progress:page_count:pitchlog_sync_right_fn_owner

GRANT SELECT (page_count),INSERT (page_count),UPDATE (page_count) ON sync_fence.p3_projection_page_progress TO pitchlog_sync_right_fn_owner;
