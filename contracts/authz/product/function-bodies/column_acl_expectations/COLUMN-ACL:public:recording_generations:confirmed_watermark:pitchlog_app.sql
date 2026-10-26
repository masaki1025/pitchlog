-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:recording_generations:confirmed_watermark:pitchlog_app

GRANT SELECT (confirmed_watermark), UPDATE (confirmed_watermark) ON TABLE public.recording_generations TO pitchlog_app;
