-- ELEMENT-TYPE: table
-- ELEMENT-ID: system_settings

ALTER TABLE public.system_settings
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_settings
    FORCE ROW LEVEL SECURITY;
