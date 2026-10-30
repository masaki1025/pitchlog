-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:players:initial_start_actor_players_select

CREATE POLICY initial_start_actor_players_select ON public.players
AS PERMISSIVE FOR SELECT TO pitchlog_initial_actor
USING (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
