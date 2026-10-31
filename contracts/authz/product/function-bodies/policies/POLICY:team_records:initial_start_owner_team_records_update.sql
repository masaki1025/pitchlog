-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:team_records:initial_start_owner_team_records_update

CREATE POLICY initial_start_owner_team_records_update ON public.team_records
AS PERMISSIVE FOR UPDATE TO pitchlog_initial_fn_owner
USING (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE))
WITH CHECK (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
