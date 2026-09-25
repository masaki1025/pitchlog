-- ELEMENT-TYPE: table
-- ELEMENT-ID: group_invitations

ALTER TABLE public.group_invitations
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.group_invitations
    FORCE ROW LEVEL SECURITY;
