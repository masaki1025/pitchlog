-- ELEMENT-TYPE: table
-- ELEMENT-ID: migration_resolution_reports

ALTER TABLE public.migration_resolution_reports
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.migration_resolution_reports
    FORCE ROW LEVEL SECURITY;
