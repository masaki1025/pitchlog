-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:lifecycle_write_admissions:codec_version:pitchlog_sync_right_fn_owner

GRANT SELECT (codec_version),INSERT (codec_version) ON TABLE sync_fence.lifecycle_write_admissions TO pitchlog_sync_right_fn_owner;
