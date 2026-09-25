-- ELEMENT-TYPE: table
-- ELEMENT-ID: migration_warning_reports

ALTER TABLE public.migration_warning_reports
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.migration_warning_reports
    FORCE ROW LEVEL SECURITY;
