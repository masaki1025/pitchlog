-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_capsules:watermark:pitchlog_sync_right_fn_owner

GRANT SELECT (watermark),INSERT (watermark) ON sync_fence.p3_projection_capsules TO pitchlog_sync_right_fn_owner;
