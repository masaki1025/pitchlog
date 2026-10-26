-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:game_start_requests:initial_right_game_start_requests_insert

CREATE POLICY initial_right_game_start_requests_insert ON public.game_start_requests
AS PERMISSIVE FOR INSERT TO pitchlog_initial_fn_owner
WITH CHECK (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
