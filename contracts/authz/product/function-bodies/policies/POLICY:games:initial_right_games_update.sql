-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:games:initial_right_games_update

CREATE POLICY initial_right_games_update ON public.games
AS PERMISSIVE FOR UPDATE TO pitchlog_initial_fn_owner
USING (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE))
WITH CHECK (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
