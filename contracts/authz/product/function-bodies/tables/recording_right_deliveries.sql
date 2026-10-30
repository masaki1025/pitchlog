-- ELEMENT-TYPE: table
-- ELEMENT-ID: recording_right_deliveries

ALTER TABLE public.recording_right_deliveries
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recording_right_deliveries
    FORCE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.recording_right_deliveries FROM PUBLIC, pitchlog_app, pitchlog_initial_actor;
