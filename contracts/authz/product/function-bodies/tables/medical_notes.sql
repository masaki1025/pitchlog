-- ELEMENT-TYPE: table
-- ELEMENT-ID: medical_notes

ALTER TABLE public.medical_notes
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.medical_notes
    FORCE ROW LEVEL SECURITY;
