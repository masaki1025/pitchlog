-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:writer_bindings:recovery_generation:pitchlog_sync_right_fn_owner

GRANT SELECT (recovery_generation) ON TABLE sync_fence.writer_bindings TO pitchlog_sync_right_fn_owner;
