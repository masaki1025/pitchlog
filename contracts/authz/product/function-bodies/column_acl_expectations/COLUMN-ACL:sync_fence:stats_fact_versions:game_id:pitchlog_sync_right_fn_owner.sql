-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:stats_fact_versions:game_id:pitchlog_sync_right_fn_owner

GRANT SELECT (game_id),INSERT (game_id) ON sync_fence.stats_fact_versions TO pitchlog_sync_right_fn_owner;
