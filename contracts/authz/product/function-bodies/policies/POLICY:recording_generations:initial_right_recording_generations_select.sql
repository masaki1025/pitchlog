-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:recording_generations:initial_right_recording_generations_select

CREATE POLICY initial_right_recording_generations_select ON public.recording_generations
AS PERMISSIVE FOR SELECT TO pitchlog_initial_fn_owner
USING (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
