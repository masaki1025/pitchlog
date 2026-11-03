-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:writer_bindings:transaction_id:pitchlog_sync_right_fn_owner

GRANT SELECT (transaction_id) ON TABLE sync_fence.writer_bindings TO pitchlog_sync_right_fn_owner;
