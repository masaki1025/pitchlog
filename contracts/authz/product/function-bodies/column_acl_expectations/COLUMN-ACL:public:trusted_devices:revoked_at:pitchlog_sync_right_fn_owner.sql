-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:trusted_devices:revoked_at:pitchlog_sync_right_fn_owner

GRANT SELECT (revoked_at) ON TABLE public.trusted_devices TO pitchlog_sync_right_fn_owner;
GRANT UPDATE (revoked_at) ON TABLE public.trusted_devices TO pitchlog_sync_right_fn_owner;
