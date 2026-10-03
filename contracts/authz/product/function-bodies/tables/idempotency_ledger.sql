-- ELEMENT-TYPE: table
-- ELEMENT-ID: idempotency_ledger

ALTER TABLE public.idempotency_ledger
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.idempotency_ledger
    FORCE ROW LEVEL SECURITY;
