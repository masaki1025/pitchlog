-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:writer_bindings:nonce_digest:pitchlog_sync_right_fn_owner

GRANT SELECT (nonce_digest) ON TABLE sync_fence.writer_bindings TO pitchlog_sync_right_fn_owner;
