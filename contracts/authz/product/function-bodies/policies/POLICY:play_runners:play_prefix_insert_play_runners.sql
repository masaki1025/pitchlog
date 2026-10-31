-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:play_runners:play_prefix_insert_play_runners

CREATE POLICY play_prefix_insert_play_runners ON public.play_runners FOR INSERT TO pitchlog_sync_right_fn_owner WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app');
