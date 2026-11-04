-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:applied_watermark:pitchlog_sync_right_fn_owner

GRANT SELECT (applied_watermark),INSERT (applied_watermark),UPDATE (applied_watermark) ON TABLE sync_fence.ordinary_pitch_checkpoints TO pitchlog_sync_right_fn_owner;
