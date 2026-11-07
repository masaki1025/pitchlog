-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:sync_fence:p3_projection_write_admissions:ledger_fingerprint:pitchlog_sync_right_fn_owner

GRANT SELECT (ledger_fingerprint),INSERT (ledger_fingerprint) ON sync_fence.p3_projection_write_admissions TO pitchlog_sync_right_fn_owner;
