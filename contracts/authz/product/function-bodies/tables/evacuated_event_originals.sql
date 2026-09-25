-- ELEMENT-TYPE: table
-- ELEMENT-ID: evacuated_event_originals

ALTER TABLE public.evacuated_event_originals
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evacuated_event_originals
    FORCE ROW LEVEL SECURITY;
