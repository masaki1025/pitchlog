-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:game_lineups:stats_basic_select

CREATE POLICY stats_basic_select ON public.game_lineups AS PERMISSIVE FOR SELECT TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app' AND current_user = 'pitchlog_sync_right_fn_owner');
