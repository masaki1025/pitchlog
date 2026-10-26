-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:game_start_attempts:initial_right_game_start_attempts_insert

CREATE POLICY initial_right_game_start_attempts_insert ON public.game_start_attempts
AS PERMISSIVE FOR INSERT TO pitchlog_initial_fn_owner
WITH CHECK (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
