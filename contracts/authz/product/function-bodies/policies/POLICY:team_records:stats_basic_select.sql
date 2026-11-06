-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:team_records:stats_basic_select

CREATE POLICY stats_basic_select ON public.team_records AS PERMISSIVE FOR SELECT TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app' AND current_user = 'pitchlog_sync_right_fn_owner');
