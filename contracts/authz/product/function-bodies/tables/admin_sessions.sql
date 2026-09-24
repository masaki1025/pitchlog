-- ELEMENT-TYPE: table
-- ELEMENT-ID: admin_sessions

ALTER TABLE public.admin_sessions
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_sessions
    FORCE ROW LEVEL SECURITY;
