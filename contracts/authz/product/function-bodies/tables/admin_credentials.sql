-- ELEMENT-TYPE: table
-- ELEMENT-ID: admin_credentials

ALTER TABLE public.admin_credentials
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_credentials
    FORCE ROW LEVEL SECURITY;
