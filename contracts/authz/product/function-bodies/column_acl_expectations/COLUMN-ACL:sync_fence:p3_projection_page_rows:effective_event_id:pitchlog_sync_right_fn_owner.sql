-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_page_rows:effective_event_id:pitchlog_sync_right_fn_owner

GRANT SELECT (effective_event_id),INSERT (effective_event_id) ON sync_fence.p3_projection_page_rows TO pitchlog_sync_right_fn_owner;
