-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:ordinary_pitch_history:history_version:pitchlog_sync_right_fn_owner

GRANT SELECT (history_version),INSERT (history_version) ON TABLE sync_fence.ordinary_pitch_history TO pitchlog_sync_right_fn_owner;
