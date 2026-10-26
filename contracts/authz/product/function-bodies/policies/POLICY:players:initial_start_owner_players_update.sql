-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:players:initial_start_owner_players_update

CREATE POLICY initial_start_owner_players_update ON public.players
AS PERMISSIVE FOR UPDATE TO pitchlog_initial_fn_owner
USING (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE))
WITH CHECK (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
