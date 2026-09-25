-- ELEMENT-TYPE: table
-- ELEMENT-ID: migration_quarantine

ALTER TABLE public.migration_quarantine
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.migration_quarantine
    FORCE ROW LEVEL SECURITY;
