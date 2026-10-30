-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:lineup_memories:initial_start_actor_lineup_memories_insert

CREATE POLICY initial_start_actor_lineup_memories_insert ON public.lineup_memories
AS PERMISSIVE FOR INSERT TO pitchlog_initial_actor
WITH CHECK (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
