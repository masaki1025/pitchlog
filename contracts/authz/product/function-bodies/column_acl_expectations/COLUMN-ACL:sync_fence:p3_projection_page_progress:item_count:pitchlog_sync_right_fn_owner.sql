-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_page_progress:item_count:pitchlog_sync_right_fn_owner

GRANT SELECT (item_count),INSERT (item_count),UPDATE (item_count) ON sync_fence.p3_projection_page_progress TO pitchlog_sync_right_fn_owner;
