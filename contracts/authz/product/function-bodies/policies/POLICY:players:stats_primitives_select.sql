-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:players:stats_primitives_select

CREATE POLICY stats_primitives_select ON public.players AS PERMISSIVE FOR SELECT TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app' AND current_user = 'pitchlog_sync_right_fn_owner');
