-- ELEMENT-TYPE: table
-- ELEMENT-ID: event_slots

ALTER TABLE public.event_slots
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.event_slots
    FORCE ROW LEVEL SECURITY;
