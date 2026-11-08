-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:play_rows:p3_finite_insert

CREATE POLICY p3_finite_insert ON public.play_rows AS PERMISSIVE FOR INSERT TO pitchlog_sync_right_fn_owner WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app');
