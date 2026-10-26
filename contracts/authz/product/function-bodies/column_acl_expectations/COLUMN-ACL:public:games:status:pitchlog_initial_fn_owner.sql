-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:games:status:pitchlog_initial_fn_owner

GRANT SELECT (status), UPDATE (status) ON TABLE public.games TO pitchlog_initial_fn_owner;
