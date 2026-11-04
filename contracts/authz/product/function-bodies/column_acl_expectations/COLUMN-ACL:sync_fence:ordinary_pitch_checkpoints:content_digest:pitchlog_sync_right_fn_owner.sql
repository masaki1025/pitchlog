-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:ordinary_pitch_checkpoints:content_digest:pitchlog_sync_right_fn_owner

GRANT SELECT (content_digest),INSERT (content_digest),UPDATE (content_digest) ON TABLE sync_fence.ordinary_pitch_checkpoints TO pitchlog_sync_right_fn_owner;
