-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_page_rows:binding_nonce:pitchlog_sync_right_fn_owner

GRANT SELECT (binding_nonce),INSERT (binding_nonce) ON sync_fence.p3_projection_page_rows TO pitchlog_sync_right_fn_owner;
