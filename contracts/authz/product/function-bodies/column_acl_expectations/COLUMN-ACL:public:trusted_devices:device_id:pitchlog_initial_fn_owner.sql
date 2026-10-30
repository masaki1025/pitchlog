-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:trusted_devices:device_id:pitchlog_initial_fn_owner

GRANT SELECT (device_id), UPDATE (device_id), INSERT (device_id) ON TABLE public.trusted_devices TO pitchlog_initial_fn_owner;
