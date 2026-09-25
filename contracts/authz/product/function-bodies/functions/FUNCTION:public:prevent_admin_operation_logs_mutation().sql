-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:public:prevent_admin_operation_logs_mutation()

REVOKE EXECUTE ON FUNCTION public.prevent_admin_operation_logs_mutation() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.prevent_admin_operation_logs_mutation() FROM pitchlog_app;
