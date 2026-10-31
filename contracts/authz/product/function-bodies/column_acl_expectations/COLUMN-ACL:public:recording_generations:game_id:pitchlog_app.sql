-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:recording_generations:game_id:pitchlog_app

GRANT SELECT (game_id), UPDATE (game_id) ON TABLE public.recording_generations TO pitchlog_app;
