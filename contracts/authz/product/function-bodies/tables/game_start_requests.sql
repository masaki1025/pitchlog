-- ELEMENT-TYPE: table
-- ELEMENT-ID: game_start_requests

ALTER TABLE public.game_start_requests
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.game_start_requests
    FORCE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.game_start_requests FROM PUBLIC, pitchlog_app, pitchlog_initial_actor;
