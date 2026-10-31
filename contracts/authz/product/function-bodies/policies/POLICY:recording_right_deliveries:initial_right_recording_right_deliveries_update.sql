-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:recording_right_deliveries:initial_right_recording_right_deliveries_update

CREATE POLICY initial_right_recording_right_deliveries_update ON public.recording_right_deliveries
AS PERMISSIVE FOR UPDATE TO pitchlog_initial_fn_owner
USING (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE))
WITH CHECK (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
