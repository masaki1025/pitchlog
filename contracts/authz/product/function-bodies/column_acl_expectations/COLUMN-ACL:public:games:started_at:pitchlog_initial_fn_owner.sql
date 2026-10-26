-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:games:started_at:pitchlog_initial_fn_owner

GRANT SELECT (started_at), UPDATE (started_at) ON TABLE public.games TO pitchlog_initial_fn_owner;
