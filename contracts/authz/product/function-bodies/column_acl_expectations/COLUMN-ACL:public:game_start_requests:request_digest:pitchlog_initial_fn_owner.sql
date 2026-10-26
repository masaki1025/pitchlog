-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:game_start_requests:request_digest:pitchlog_initial_fn_owner

GRANT SELECT (request_digest), INSERT (request_digest) ON TABLE public.game_start_requests TO pitchlog_initial_fn_owner;
