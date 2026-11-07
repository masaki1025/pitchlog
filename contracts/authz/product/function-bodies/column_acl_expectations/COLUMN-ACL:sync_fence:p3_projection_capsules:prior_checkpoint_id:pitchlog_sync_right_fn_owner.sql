-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_capsules:prior_checkpoint_id:pitchlog_sync_right_fn_owner

GRANT SELECT (prior_checkpoint_id),INSERT (prior_checkpoint_id) ON sync_fence.p3_projection_capsules TO pitchlog_sync_right_fn_owner;
