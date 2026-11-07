-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_page_progress:tenant_id:pitchlog_sync_right_fn_owner

GRANT SELECT (tenant_id),INSERT (tenant_id) ON sync_fence.p3_projection_page_progress TO pitchlog_sync_right_fn_owner;
