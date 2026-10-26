-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:team_records:initial_start_actor_team_records_select

CREATE POLICY initial_start_actor_team_records_select ON public.team_records
AS PERMISSIVE FOR SELECT TO pitchlog_initial_actor
USING (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
