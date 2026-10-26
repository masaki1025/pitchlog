-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:public:game_lineups:tenant_id:pitchlog_initial_fn_owner

GRANT SELECT (tenant_id), INSERT (tenant_id) ON TABLE public.game_lineups TO pitchlog_initial_fn_owner;
