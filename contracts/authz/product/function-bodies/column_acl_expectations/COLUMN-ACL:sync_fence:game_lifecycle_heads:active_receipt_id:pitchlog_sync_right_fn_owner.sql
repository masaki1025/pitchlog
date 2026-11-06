-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:game_lifecycle_heads:active_receipt_id:pitchlog_sync_right_fn_owner

GRANT SELECT (active_receipt_id),INSERT (active_receipt_id),UPDATE (active_receipt_id) ON TABLE sync_fence.game_lifecycle_heads TO pitchlog_sync_right_fn_owner;
