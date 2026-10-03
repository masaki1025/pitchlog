-- ELEMENT-TYPE: table
-- ELEMENT-ID: tenant_vocabularies

ALTER TABLE public.tenant_vocabularies
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tenant_vocabularies
    FORCE ROW LEVEL SECURITY;
