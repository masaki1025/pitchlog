-- ELEMENT-TYPE: table
-- ELEMENT-ID: rate_limit_counters

ALTER TABLE public.rate_limit_counters
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rate_limit_counters
    FORCE ROW LEVEL SECURITY;
