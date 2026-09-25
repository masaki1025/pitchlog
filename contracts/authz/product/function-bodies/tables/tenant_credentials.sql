-- ELEMENT-TYPE: table
-- ELEMENT-ID: tenant_credentials

ALTER TABLE public.tenant_credentials
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tenant_credentials
    FORCE ROW LEVEL SECURITY;
