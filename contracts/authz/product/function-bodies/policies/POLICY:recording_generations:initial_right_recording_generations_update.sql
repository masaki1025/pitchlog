-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:recording_generations:initial_right_recording_generations_update

CREATE POLICY initial_right_recording_generations_update ON public.recording_generations
AS PERMISSIVE FOR UPDATE TO pitchlog_initial_fn_owner
USING (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE))
WITH CHECK (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
