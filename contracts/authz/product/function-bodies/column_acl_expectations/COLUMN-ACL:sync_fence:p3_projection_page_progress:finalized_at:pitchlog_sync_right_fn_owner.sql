-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_page_progress:finalized_at:pitchlog_sync_right_fn_owner

GRANT SELECT (finalized_at),INSERT (finalized_at),UPDATE (finalized_at) ON sync_fence.p3_projection_page_progress TO pitchlog_sync_right_fn_owner;
