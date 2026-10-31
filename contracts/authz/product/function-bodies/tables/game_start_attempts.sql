-- ELEMENT-TYPE: table
-- ELEMENT-ID: game_start_attempts

ALTER TABLE public.game_start_attempts
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.game_start_attempts
    FORCE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.game_start_attempts FROM PUBLIC, pitchlog_app, pitchlog_initial_actor;
