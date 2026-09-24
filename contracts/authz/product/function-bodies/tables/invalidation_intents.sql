-- ELEMENT-TYPE: table
-- ELEMENT-ID: invalidation_intents

ALTER TABLE public.invalidation_intents
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.invalidation_intents
    FORCE ROW LEVEL SECURITY;
