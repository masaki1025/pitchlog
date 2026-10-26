-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:game_start_requests:device_id:pitchlog_initial_fn_owner

GRANT SELECT (device_id), INSERT (device_id) ON TABLE public.game_start_requests TO pitchlog_initial_fn_owner;
