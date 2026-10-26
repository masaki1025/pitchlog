-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:recording_right_deliveries:game_id:pitchlog_initial_fn_owner

GRANT SELECT (game_id), INSERT (game_id) ON TABLE public.recording_right_deliveries TO pitchlog_initial_fn_owner;
