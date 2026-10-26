-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:trusted_devices:credential_digest:pitchlog_initial_fn_owner

GRANT SELECT (credential_digest), INSERT (credential_digest) ON TABLE public.trusted_devices TO pitchlog_initial_fn_owner;
