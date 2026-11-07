-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_page_progress:source_page_seal:pitchlog_sync_right_fn_owner

GRANT SELECT (source_page_seal),INSERT (source_page_seal),UPDATE (source_page_seal) ON sync_fence.p3_projection_page_progress TO pitchlog_sync_right_fn_owner;
