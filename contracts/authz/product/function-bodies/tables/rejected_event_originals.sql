-- ELEMENT-TYPE: table
-- ELEMENT-ID: rejected_event_originals

ALTER TABLE public.rejected_event_originals
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rejected_event_originals
    FORCE ROW LEVEL SECURITY;
