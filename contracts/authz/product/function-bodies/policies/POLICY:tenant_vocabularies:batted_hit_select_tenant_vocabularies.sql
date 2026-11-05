-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:tenant_vocabularies:batted_hit_select_tenant_vocabularies

CREATE POLICY batted_hit_select_tenant_vocabularies ON public.tenant_vocabularies AS PERMISSIVE FOR SELECT TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app');
