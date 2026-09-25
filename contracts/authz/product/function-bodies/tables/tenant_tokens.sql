-- ELEMENT-TYPE: table
-- ELEMENT-ID: tenant_tokens

ALTER TABLE public.tenant_tokens
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tenant_tokens
    FORCE ROW LEVEL SECURITY;
