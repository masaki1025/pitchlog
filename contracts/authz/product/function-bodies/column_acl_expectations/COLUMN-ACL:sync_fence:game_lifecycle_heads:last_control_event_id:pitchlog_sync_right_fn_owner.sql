-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:game_lifecycle_heads:last_control_event_id:pitchlog_sync_right_fn_owner

GRANT SELECT (last_control_event_id),INSERT (last_control_event_id),UPDATE (last_control_event_id) ON TABLE sync_fence.game_lifecycle_heads TO pitchlog_sync_right_fn_owner;
