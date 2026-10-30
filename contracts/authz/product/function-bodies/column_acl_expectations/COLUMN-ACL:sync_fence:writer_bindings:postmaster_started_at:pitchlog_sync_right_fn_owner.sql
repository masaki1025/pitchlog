-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:writer_bindings:postmaster_started_at:pitchlog_sync_right_fn_owner

GRANT SELECT (postmaster_started_at) ON TABLE sync_fence.writer_bindings TO pitchlog_sync_right_fn_owner;
