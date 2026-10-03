-- ELEMENT-TYPE: table
-- ELEMENT-ID: tenant_auth_subjects

ALTER TABLE public.tenant_auth_subjects
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tenant_auth_subjects
    FORCE ROW LEVEL SECURITY;
