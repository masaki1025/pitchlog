-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:games:initial_right_games_select

CREATE POLICY initial_right_games_select ON public.games
AS PERMISSIVE FOR SELECT TO pitchlog_initial_fn_owner
USING (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
