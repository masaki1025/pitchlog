-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:recording_right_deliveries:initial_right_recording_right_deliveries_insert

CREATE POLICY initial_right_recording_right_deliveries_insert ON public.recording_right_deliveries
AS PERMISSIVE FOR INSERT TO pitchlog_initial_fn_owner
WITH CHECK (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
