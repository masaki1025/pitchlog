-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_page_progress:created_at:pitchlog_sync_right_fn_owner

GRANT SELECT (created_at),INSERT (created_at) ON sync_fence.p3_projection_page_progress TO pitchlog_sync_right_fn_owner;
