-- ELEMENT-TYPE: table
-- ELEMENT-ID: admin_operation_logs

ALTER TABLE public.admin_operation_logs
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_operation_logs
    FORCE ROW LEVEL SECURITY;
