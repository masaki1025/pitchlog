-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_page_rows:attempt_id:pitchlog_sync_right_fn_owner

GRANT SELECT (attempt_id),INSERT (attempt_id) ON sync_fence.p3_projection_page_rows TO pitchlog_sync_right_fn_owner;
