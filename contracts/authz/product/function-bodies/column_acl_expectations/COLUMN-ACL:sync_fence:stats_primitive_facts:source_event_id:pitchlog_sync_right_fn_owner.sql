-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_primitive_facts:source_event_id:pitchlog_sync_right_fn_owner

GRANT SELECT (source_event_id),INSERT (source_event_id) ON sync_fence.stats_primitive_facts TO pitchlog_sync_right_fn_owner;
