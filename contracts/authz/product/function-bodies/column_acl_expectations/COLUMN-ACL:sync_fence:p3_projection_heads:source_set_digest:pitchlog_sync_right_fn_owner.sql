-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_heads:source_set_digest:pitchlog_sync_right_fn_owner

GRANT SELECT (source_set_digest),INSERT (source_set_digest),UPDATE (source_set_digest) ON sync_fence.p3_projection_heads TO pitchlog_sync_right_fn_owner;
