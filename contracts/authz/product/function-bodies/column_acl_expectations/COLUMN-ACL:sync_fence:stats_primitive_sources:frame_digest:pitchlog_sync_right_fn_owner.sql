-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_primitive_sources:frame_digest:pitchlog_sync_right_fn_owner

GRANT SELECT (frame_digest),INSERT (frame_digest) ON sync_fence.stats_primitive_sources TO pitchlog_sync_right_fn_owner;
