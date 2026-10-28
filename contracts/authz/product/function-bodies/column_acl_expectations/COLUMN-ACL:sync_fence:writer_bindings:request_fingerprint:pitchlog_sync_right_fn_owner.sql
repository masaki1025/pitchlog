-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:writer_bindings:request_fingerprint:pitchlog_sync_right_fn_owner

GRANT SELECT (request_fingerprint) ON TABLE sync_fence.writer_bindings TO pitchlog_sync_right_fn_owner;
