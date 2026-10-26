-- ELEMENT-TYPE: table
-- ELEMENT-ID: trusted_devices

ALTER TABLE public.trusted_devices
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trusted_devices
    FORCE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.trusted_devices FROM PUBLIC, pitchlog_app, pitchlog_initial_actor;
