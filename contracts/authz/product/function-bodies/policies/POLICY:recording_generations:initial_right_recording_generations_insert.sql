-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:recording_generations:initial_right_recording_generations_insert

CREATE POLICY initial_right_recording_generations_insert ON public.recording_generations
AS PERMISSIVE FOR INSERT TO pitchlog_initial_fn_owner
WITH CHECK (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
