-- ELEMENT-TYPE: table
-- ELEMENT-ID: group_memberships

ALTER TABLE public.group_memberships
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.group_memberships
    FORCE ROW LEVEL SECURITY;
