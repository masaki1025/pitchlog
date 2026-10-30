-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:confirmed_watermark:pitchlog_sync_right_fn_owner

GRANT SELECT (confirmed_watermark),INSERT (confirmed_watermark),UPDATE (confirmed_watermark) ON TABLE sync_fence.ordinary_pitch_checkpoints TO pitchlog_sync_right_fn_owner;
