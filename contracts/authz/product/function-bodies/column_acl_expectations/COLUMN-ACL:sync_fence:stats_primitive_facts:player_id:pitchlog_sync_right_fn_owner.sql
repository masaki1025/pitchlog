-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_primitive_facts:player_id:pitchlog_sync_right_fn_owner

GRANT SELECT (player_id),INSERT (player_id) ON sync_fence.stats_primitive_facts TO pitchlog_sync_right_fn_owner;
