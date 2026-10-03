-- ELEMENT-TYPE: table
-- ELEMENT-ID: sharing_grants

ALTER TABLE public.sharing_grants
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sharing_grants
    FORCE ROW LEVEL SECURITY;
