-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:writer_bindings:lease_id:pitchlog_sync_right_fn_owner

GRANT SELECT (lease_id) ON TABLE sync_fence.writer_bindings TO pitchlog_sync_right_fn_owner;
