-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:game_start_requests:initial_right_game_start_requests_update

CREATE POLICY initial_right_game_start_requests_update ON public.game_start_requests
AS PERMISSIVE FOR UPDATE TO pitchlog_initial_fn_owner
USING (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE))
WITH CHECK (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
