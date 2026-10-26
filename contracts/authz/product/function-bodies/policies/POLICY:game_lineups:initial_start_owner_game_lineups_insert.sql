-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:game_lineups:initial_start_owner_game_lineups_insert

CREATE POLICY initial_start_owner_game_lineups_insert ON public.game_lineups
AS PERMISSIVE FOR INSERT TO pitchlog_initial_fn_owner
WITH CHECK (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
