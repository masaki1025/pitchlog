-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_capsules:prior_checkpoint_digest:pitchlog_sync_right_fn_owner

GRANT SELECT (prior_checkpoint_digest),INSERT (prior_checkpoint_digest) ON sync_fence.p3_projection_capsules TO pitchlog_sync_right_fn_owner;
