-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_page_progress:watermark:pitchlog_sync_right_fn_owner

GRANT SELECT (watermark),INSERT (watermark) ON sync_fence.p3_projection_page_progress TO pitchlog_sync_right_fn_owner;
