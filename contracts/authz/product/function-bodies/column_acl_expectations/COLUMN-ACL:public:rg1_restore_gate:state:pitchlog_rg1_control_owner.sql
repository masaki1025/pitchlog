-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:rg1_restore_gate:state:pitchlog_rg1_control_owner

GRANT SELECT (state), UPDATE (state) ON TABLE public.rg1_restore_gate TO pitchlog_rg1_control_owner;
