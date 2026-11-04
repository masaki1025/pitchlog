-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:game_start_attempts:lineup_prefix_game_start_attempts_select

CREATE POLICY lineup_prefix_game_start_attempts_select ON public.game_start_attempts FOR SELECT TO pitchlog_sync_right_fn_owner USING (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
