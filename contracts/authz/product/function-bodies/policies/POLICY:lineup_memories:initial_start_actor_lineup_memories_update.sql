-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:lineup_memories:initial_start_actor_lineup_memories_update

CREATE POLICY initial_start_actor_lineup_memories_update ON public.lineup_memories
AS PERMISSIVE FOR UPDATE TO pitchlog_initial_actor
USING (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE))
WITH CHECK (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
