-- ELEMENT-TYPE: table
-- ELEMENT-ID: migration_runs

ALTER TABLE public.migration_runs
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.migration_runs
    FORCE ROW LEVEL SECURITY;
