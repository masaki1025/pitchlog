-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:game_lifecycle_heads:active_end_event_id:pitchlog_sync_right_fn_owner

GRANT SELECT (active_end_event_id),INSERT (active_end_event_id),UPDATE (active_end_event_id) ON TABLE sync_fence.game_lifecycle_heads TO pitchlog_sync_right_fn_owner;
